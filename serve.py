#!/usr/bin/python3

#todo serve from multiple folders
#     -change all executables to be extension sqhashed?
#     -add basic credential manager

import argparse
import codecs
import collections
import json
import os
import ssl
import stat
import subprocess as sp
import threading
import traceback

from cgi import parse_header, parse_multipart
from http.server import HTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from lrudict import LRUDict
from pathlib import Path
from httpsredirecthandler import HTTPSRedirectHandler
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

src_dir = Path(__file__).parent
path_cache = LRUDict(timeout=60)

class WWWData:
    def __init__(self, path, base=''):
        self.path = Path(path)
        self.path.resolve(strict=True)
        self.base = Path(base)

if __name__ == '__main__':
    parser = argparse.ArgumentParser("Simple python server")
    parser.add_argument('--debug', '-g', action='store_true')
    parser.add_argument('--buf_size', type=int, default=1024*1024)
    parser.add_argument('--cert', default=None)
    parser.add_argument('--cfg', default=str(src_dir / 'default_cfg.json'))
    parser.add_argument('--http_port', type=int, default=80)
    parser.add_argument('--https_port', type=int, default=443)
    parser.add_argument('--no_redirect', action='store_true')
    parser.add_argument('--gen_cert', default=None)
    parser.add_argument('www', nargs='*')
    args = parser.parse_args()
    www = []
    for w in args.www:
        www += [WWWData(*w.split(':'))]
    args.www = www
    del www
    if args.cert is not None:
        args.cert = Path(args.cert)

with open(args.cfg, 'r') as f:
    cfg = json.load(f)

cwd = Path(os.getcwd())
cwd.resolve(strict=True)

def escape(val):
    return codecs.getencoder('unicode_escape')(val)[0]

def path_in_parent(path, parent):
    try:
        return not str(path.relative_to(parent)).startswith('..')
    except ValueError:
        return False

class RequestHandler(BaseHTTPRequestHandler):
    def __init__(self, *pargs, **kwargs):
        super().__init__(*pargs, **kwargs)

    def run_resp(self, code=200, data=None, mime=None, cookies=None, headers=None):
        if isinstance(data, Path):
            try:
                f = data.open('rb')
            except:
                if args.debug:
                    self.run_resp(500, traceback.format_exc(), 'text/plain')
                else:
                    self.run_resp(500)
        self.send_response(code)

        if mime is not None:
            self.send_header('Content-Type', mime)

        if cookies is not None:
            for c in cookies:
                self.send_header('Set-Cookie', c)

        if headers is not None:
            for h in headers:
                self.send_header(*h)


        if isinstance(data, Path):
            self.send_header('Content-Length', os.path.getsize(data))
        elif data is not None:
            if isinstance(data, str):
                data = data.encode()
            self.send_header('Content-Length', len(data))
        self.end_headers()

        if isinstance(data, Path):
            try:
                data = f.read(args.buf_size)
                while data is not None and len(data) > 0:
                    self.wfile.write(data)
                    data = f.read(args.buf_size)
            finally:
                f.close()
        elif data is not None:
            self.wfile.write(data)

    def path_check(self, base: Path, file: Path, url: Path):
        file.resolve(strict=True)
        base.resolve(strict=True)
        if not path_in_parent(file, base):
            return None, None
        if file.is_dir() and 'index' in cfg:
            for f in file.iterdir():
                for i in cfg['index']:
                    fret, ext = self.path_check(base, f, url/i)
                    if fret is not None:
                        return fret, ext
            return None, None
        if file.name != url.name and not os.access(file, os.X_OK):
            return None, None
        elif file.name != url.name and not file.name.startswith(url.name + '.'):
            return None, None
        url_ext = url.name.split('.')
        if len(url_ext) > 1:
            return file, '.' + '.'.join(url_ext[1:])
        else:
            return file, url_ext[0]

    def path_lookup(self, path):
        path = Path(path)
        with path_cache:
            if path in path_cache:
                (fret, ext) = path_cache[path]
                if not fret.is_file():
                    del path_cache[path]
                else:
                    return fret, ext
        for site in args.www:
            if len(path.parts) < len(site.base.parts) or path.parts[:len(site.base.parts)] != site.base.parts:
                continue
            lpath = path.relative_to(site.base)
            dpath = (site.path / lpath)
            if dpath == site.path:
                fret, ext = self.path_check(site.path, dpath, lpath)
                path_cache[path] = (fret, ext)
                return fret, ext
            else:
                dpath = dpath.parent
            for file in dpath.iterdir():
                fret, ext = self.path_check(site.path, file, lpath)
                if fret is not None:
                    path_cache[path] = (fret, ext)
                    return fret, ext
        return None, None

    def run_head(self):
        o = urlparse(self.path)
        self.url_get = parse_qs(o.query)
        path = o.path
        if path.startswith('/'):
            path = path[1:]
        path, ftype = self.path_lookup(path)
        if path is None:
            self.run_resp(404)
            return None, None
        while '.' in ftype[1:]:
            if ftype in cfg['file_types']:
                break
            ftype = ftype[ftype[1:].index('.')+1:]
        if ftype in cfg['file_types']:
            mime = cfg['file_types'][ftype]
        else:
            mime = cfg['file_types']['*']
        return path, mime

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
        return postvars

    def do_exec(self, path, mime, post_vars=None):
        exec_input = b''
        cookies = SimpleCookie(self.headers.get('Cookie'))
        env = {}
        for k in cookies:
            if k.isidentifier():
                continue
            env['COOKIE_' + k] = cookies[k].value
        cmd_args = {}
        if post_vars is None:
            for k in self.url_get:
                if not k.isidentifier():
                    continue
                n = '--' + k.replace('_', '-')
                cmd_args[n] = [val for val in self.url_get[k] if val != b'']
        else:
            for k in post_vars:
                if not k.decode().isidentifier():
                    continue
                n = '--' + k.decode().replace('_', '-')
                cmd_args[n] = [val.decode() for val in post_vars[k] if val != b'']
        try:
            cmd = [src_dir / 'run.sh', path]
            for k in cmd_args:
                cmd += [k] + cmd_args[k]
            val = sp.run(cmd, env=env, check=True, stdout=sp.PIPE, stderr=sp.PIPE, timeout=10)
            dmp = val.stderr.decode().split('\0')
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
            self.run_resp(200, val.stdout, mime, cookies=cookies, headers=headers)
        except sp.CalledProcessError as err:
            if args.debug:
                self.run_resp(500, b'execution error:\n' + err.stderr, 'text/plain')
            else:
                self.run_resp(500)
        except:
            if args.debug:
                self.run_resp(500, 'server error:\n' + traceback.format_exc(), 'text/plain')
            else:
                self.run_resp(500)

    def do_HEAD(self):
        self.run_head()

    def do_GET(self):
        path, mime = self.run_head()
        if path is None:
            return
        if os.access(path, os.X_OK):
            self.do_exec(path, mime)
        else:
            self.run_resp(200, path, mime)

    def do_POST(self):
        path, mime = self.run_head()
        if path is None:
            return
        if os.access(path, os.X_OK):
            self.do_exec(path, mime, self.parse_POST())
        else:
            self.run_resp(200, path, mime)
		

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

if __name__ == '__main__':
    if args.gen_cert is not None:
        cert_folder = Path(args.gen_cert)
        if not cert_folder.exists():
            os.mkdir(cert_folder)
        sp.check_call(['openssl', 'req', '-x509', '-nodes', '-days', '365', '-newkey', 'rsa:2048', '-keyout',
                       str(cert_folder/'key.pem'), '-out', str(cert_folder/'cert.pem')])
        exit(0)
    if args.cert is not None:
        print('starting https')
        th_redir = None
        httpd = None
        if not args.no_redirect:
            httpd = ThreadedHTTPServer(('', args.http_port), HTTPSRedirectHandler(args.https_port))
            th_redir = threading.Thread(target=httpd.serve_forever)
            th_redir.start()
        httpsd = ThreadedHTTPServer(('', args.https_port), RequestHandler)
        httpsd.socket = ssl.wrap_socket(httpsd.socket, certfile=args.cert/'cert.pem', keyfile=args.cert/'key.pem',
                                        server_side=True)
        try:
            httpsd.serve_forever()
        finally:
            if httpd:
                httpd.shutdown()
    else:
        print('starting http')
        httpd = ThreadedHTTPServer(('', args.http_port), RequestHandler)
        httpd.serve_forever()
