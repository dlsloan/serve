#!/usr/bin/python3

# todo
#     -add basic credential manager

import argparse
import os
import ssl
import threading

from http.server import HTTPServer
from pathlib import Path
from httpsredirecthandler import HTTPSRedirectHandler
from socketserver import ThreadingMixIn
from requesthandler import RequestHandler

src_dir = Path(__file__).parent

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

cwd = Path(os.getcwd())
cwd.resolve(strict=True)
		

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
        httpsd = ThreadedHTTPServer(('', args.https_port), RequestHandler(args.www, args.cfg, args.buf_size, args.debug))
        httpsd.socket = ssl.wrap_socket(httpsd.socket, certfile=args.cert/'cert.pem', keyfile=args.cert/'key.pem',
                                        server_side=True)
        try:
            httpsd.serve_forever()
        finally:
            if httpd:
                httpd.shutdown()
    else:
        print('starting http')
        httpd = ThreadedHTTPServer(('', args.http_port), RequestHandler(args.www, args.cfg, args.buf_size, args.debug))
        httpd.serve_forever()
