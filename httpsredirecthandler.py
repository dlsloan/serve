from functools import partial
from http.server import BaseHTTPRequestHandler

def HTTPSRedirectHandler(https_port, *pargs, **kwargs):
    return partial(_HTTPSRedirectHandler, https_port, *pargs, **kwargs)

class _HTTPSRedirectHandler(BaseHTTPRequestHandler):
    def __init__(self, https_port, *pargs, **kwargs):
        self.https_port = https_port
        super().__init__(*pargs, **kwargs)

    def do_HEAD(self):
        self.do_redirect(301)

    def do_GET(self):
        self.do_HEAD()

    def do_POST(self):
        self.do_redirect(303)

    def do_redirect(self, code):
        host = self.headers['Host']
        if ':' in host:
            host = f"{host.split(':')[-2]}:{self.https_port}"
        else:
            host = f"{host}:{self.https_port}"
        while self.path.startswith('/'):
            self.path = self.path[1:]
        self.send_response(code)
        if not self.path.startswith('/') and self.path != '':
            self.path = '/' + self.path
        self.send_header('location', f"https://{host}{self.path}")
        self.end_headers()