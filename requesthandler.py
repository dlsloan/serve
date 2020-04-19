import json
import os
import pwd
import subprocess as sp
import traceback

from cgi import parse_header, parse_multipart
from functools import partial
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from lrudict import LRUDict
from urllib.parse import parse_qs, urlparse
from webcfg import WebCFG
from webresource import WebResource

src_dir = Path(__file__).parent

path_cache = LRUDict(timeout=60)

def RequestHandler(webcfg, buf_size=1024*1024, debug=False, *pargs, **kwargs):
    return partial(_RequestHandler, webcfg, buf_size, debug, *pargs, **kwargs)

class _RequestHandler(BaseHTTPRequestHandler):
    def __init__(self, webcfg, buf_size, debug, *pargs, **kwargs):
        self.webcfg = webcfg
        self.buf_size = buf_size
        self.debug = debug
        super().__init__(*pargs, **kwargs)

    def send_data(self, code=200, data=None, length=None, resource=None, cookies=None, headers=None):
        if isinstance(data, str):
            data = data.encode()
        self.send_response(code)
        if resource is not None:
            self.send_header('Content-Type', resource.mime)
        if cookies is not None:
            for c in cookies:
                self.send_header('Set-Cookie', c)
        if headers is not None:
            for h in headers:
                self.send_header(*h)
        if length is None and data is not None:
            length = len(data)
        if length is not None:
            self.send_header('Content-Length', length)
        self.end_headers()
        if isinstance(data, (bytes, bytearray)):
            self.send_header('Content-Length', len(data))
            self.wfile.write(data)
        elif data is not None:
            self.send_header('Content-Length', length)
            val = data.read(self.buf_size)
            while val is not None and len(val) > 0:
                self.wfile.write(val)
                val = data.read(self.buf_size)

    def lookup_resource(self, url_path:Path):
        ret = path_cache[str(url_path)]
        if ret is not None:
            return ret
        fpath = self.webcfg.find_file(url_path)
        if fpath is None:
            return None
        ret = WebResource(url_path, fpath, self.webcfg)
        path_cache[str(url_path)] = ret
        return ret

    def run_head(self, post=False):
        self.env = {}
        web_path = self.parse_url()
        resource = self.lookup_resource(web_path)
        if resource is None:
            self.send_data(404)
            return None
        if post:
            self.parse_POST()
        else:
            self.post_params = None
        self.parse_cookies()
        return resource

    def do_HEAD(self):
        resource = self.run_head()
        if resource is None:
            return
        self.send_data()

    def do_GET(self):
        self._do_REQ(post=False)

    def do_POST(self):
        self._do_REQ(post=True)

    def _do_REQ(self, post):
        resource = self.run_head(post=post)
        if resource is None:
            return
        if os.access(resource.local_path, os.X_OK):
            self.do_exec(resource)
        else:
            self.do_file(resource)

    def parse_url(self):
        o = urlparse(self.path)
        url_get = parse_qs(o.query)
        path = o.path
        if not path.startswith('/'):
            path = '/' + path
        self.get_params = url_get
        return Path(path)

    def parse_POST(self):
        ctype, pdict = parse_header(self.headers['content-type'])
        if ctype == 'multipart/form-data':
            postvars = parse_multipart(self.rfile, pdict)
        elif ctype == 'application/x-www-form-urlencoded':
            length = int(self.headers['content-length'])
            postvars = parse_qs(
                    self.rfile.read(length), 
                    keep_blank_values=1)
        else:
            postvars = {}
        # convert from bytes
        self.post_params = {}
        for k in postvars:
            self.post_params[k.decode()] = list(v.decode() for v in postvars[k])

    def parse_cookies(self):
        cookies = SimpleCookie(self.headers.get('Cookie'))
        for k in cookies:
            if k.isidentifier():
                continue
            self.env['COOKIE_' + k] = cookies[k].value

    def do_file(self, resource):
        try:
            f = resource.local_path.open('rb')
        except:
            path_cache.remove(str(resource.web_path))
            if self.debug:
                self.send_data(500, b'execution error:\n' + err.stderr, 'text/plain')
            else:
                self.send_data(500)
            return
        try:
            self.send_data(data=f, length=resource.local_path.stat().st_size, resource=resource)
        finally:
            f.close()

    def do_exec(self, resource, post_vars=None):
        exec_input = b''
        cmd_args = {}
        cmd_vars = self.get_params if self.post_params is None else self.post_params
        for k in cmd_vars:
            if not k.isidentifier():
                continue
            n = '--' + k.replace('_', '-')
            cmd_args[n] = [val for val in cmd_vars[k] if val != '']
        try:
            cmd = [src_dir / 'run.sh', str(resource.local_path)]
            for k in cmd_args:
                cmd += [k] + cmd_args[k]
            val = sp.run(cmd, env=self.env, check=True, stdout=sp.PIPE, stderr=sp.PIPE, timeout=10)
            cookies, headers = self.parse_exec_env(val.stderr)
            self.send_data(200, data=val.stdout, resource=resource, cookies=cookies, headers=headers)
        except sp.CalledProcessError as err:
            path_cache.remove(str(resource.web_path))
            if self.debug:
                self.send_data(500, b'execution error:\n' + err.stderr, 'text/plain')
            else:
                self.send_data(500)
        except:
            path_cache.remove(str(resource.web_path))
            if self.debug:
                self.send_data(500, 'server error:\n' + traceback.format_exc(), 'text/plain')
            else:
                self.send_data(500)

    def parse_exec_env(self, stderr):
        dmp = stderr.decode().split('\0')
        env_parts = dmp[len(dmp) - dmp[::-1].index('----------ENV----------\n'):]
        cookies = []
        headers = []
        for e in env_parts:
            if '=' not in e:
                continue
            name = e[:e.index('=')]
            value = e[len(name)+1:]
            if name.startswith('COOKIE_'):
                name = name[7:]
                cookies += [f"{name}={value}"]
            elif name == 'CACHE_CONTROL':
                headers += [f"Cache-Control: {value}"]
                parts = line.split(':')
                headers += [[parts[0].strip(), parts[1].strip()]]
        return cookies, headers
