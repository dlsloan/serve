#!/usr/bin/python3

#todo serve from multiple folders, double extension squashing (separate mime type from execution is index.html.py -> index.html generated from python)
#     allow get requests on extension squashed files
#stderr CACHED:No

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
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

def escape(val):
	return codecs.getencoder('unicode_escape')(val)[0]

scr_dir = Path(__file__).parent

cfg = {}

with open(scr_dir / 'default_cfg.json', 'r') as f:
	cfg = json.load(f)

if __name__ == '__main__':
	parser = argparse.ArgumentParser("Simple python server")
	parser.add_argument('--cwd', default=None)
	parser.add_argument('--debug', '-g', action='store_true')
	parser.add_argument('--buf_size', type=int, default=1024*1024)
	args = parser.parse_args()
	if args.cwd is not None:
		os.chdir(args.cwd)

cwd = Path(os.getcwd())
cwd.resolve(strict=True)

if (cwd / 'cfg.json').is_file():
	with open(cwd / 'cfg.json', 'r') as f:
		cfg_usr = json.load(f)
	for k in cfg_usr:
		if k in cfg and isinstance(cfg[k], collections.Mapping):
			cfg[k].update(cfg_usr[k])
		else:
			cfg[k] = cfg_usr[k]
	del cfg_usr

class RedirectHandler(BaseHTTPRequestHandler):
	def __init__(self, *pargs, **kwargs):
		super().__init__(*pargs, **kwargs)

	def do_HEAD(self):
		self.do_redirect(301)

	def do_GET(self):
		self.do_HEAD()

	def do_POST(self):
		self.do_redirect(303)

	def do_redirect(self, code):
		host = self.headers['Host']
		host = host.split(':')[-2] + ":56443"
		while self.path.startswith('/'):
			self.path = self.path[1:]
		self.send_response(code)
		if not self.path.startswith('/') and self.path != '':
			self.path = '/' + self.path
		self.send_header('location', 'https://' + host + self.path)
		self.end_headers()

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


	def run_head(self, exec=False):
		o = urlparse(self.path)
		self.url_get = parse_qs(o.query)
		path = o.path
		if path.startswith('/'):
			path = path[1:]
		path = cwd / path
		path.resolve(strict=False)
		for p in path.parents:
			if p.name.startswith('.'):
				self.run_resp(404)
				return None, None
		if not path_in_parent(path, cwd):
			self.run_resp(403)
			return None, None
		elif not path.exists() or path.name.startswith('.'):
			self.run_resp(404)
			return None, None
		elif path.is_dir():
			if 'index' in cfg:
				index = cfg['index']
			else:
				index = []
			found = False
			for i in index:
				fpath = path / i
				if not fpath.is_file():
					continue
				elif exec and not os.access(fpath, os.X_OK):
					continue
				elif not exec and os.access(fpath, os.X_OK):
					continue
				path = fpath
				found = True
				break
			if not found:
				self.run_resp(404)
				return None, None
		elif path.is_file():
			if exec and not os.access(path, os.X_OK):
				self.run_resp(404)
				return None, None
			elif not exec and os.access(path, os.X_OK):
				self.run_resp(404)
				return None, None
		parts = str(path.name).split('.')
		if len(parts) == 1:
			ftype = parts[-1]
		else:
			ftype = '.' + parts[-1]
		if ftype in cfg['file_types']:
			mime = cfg['file_types'][ftype]
		else:
			mime = cfg['file_types']['*']
		return path, mime

	def do_HEAD(self):
		self.run_head(False)

	def do_GET(self):
		path, mime = self.run_head(False)
		if path is None:
			return
		self.run_resp(200, path, mime)

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

	def do_POST(self):
		path, mime = self.run_head(True)
		if path is None:
			return
		exec_input = b''
		cookies = SimpleCookie(self.headers.get('Cookie'))
		for k in cookies:
			name = escape(k)
			val = escape(cookies[k].value)
			exec_input += b'COOKIE:"' + name + b'"="' + val + b'"\n'
		post_vars = self.parse_POST()
		for k in post_vars:
			name = escape(k.decode())
			for i in post_vars[k]:
				val = escape(i.decode())
				exec_input += b'POST:"' + name + b'"="' + val + b'"\n'
		for k in self.url_get:
			name = escape(k)
			for i in self.url_get[k]:
				val = escape(i)
				exec_input += b'GET:"' + name + b'"="' + val + b'"\n'
		try:
			val = sp.run([path], input=exec_input, check=True, stdout=sp.PIPE, stderr=sp.PIPE, timeout=10)
			cookies = []
			headers = []
			for line in val.stderr.decode().split('\n'):
				line = line.strip()
				if line.startswith('COOKIE:'):
					c = line[line.index(':')+1:].strip()
					for k in c:
						cookies += [c]
				elif line.startswith("Cache-Control:"):
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

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

if __name__ == '__main__':
	if (cwd / '.auth').is_dir():
		print('starting https')
		httpd = ThreadedHTTPServer(('', 56080), RedirectHandler)
		th_redir = threading.Thread(target=httpd.serve_forever)
		th_redir.start()
		httpsd = ThreadedHTTPServer(('', 56443), RequestHandler)
		httpsd.socket = ssl.wrap_socket(httpsd.socket, certfile=cwd/'.auth'/'serve.pem', server_side=True)
	else:
		print('starting http')
		httpd = ThreadedHTTPServer(('', 56080), RequestHandler)
		httpd.serve_forever()
