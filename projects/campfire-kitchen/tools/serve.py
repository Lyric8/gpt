#!/usr/bin/env python3
"""Optional standard-library HTTP server. Running the HTML normally needs no server."""
from __future__ import annotations
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import sys
import webbrowser

ROOT = Path(__file__).resolve().parents[1]

class Handler(SimpleHTTPRequestHandler):
    def list_directory(self, path):
        self.send_error(403, 'Directory listings are disabled')
        return None

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--lan', action='store_true', help='Expose only on your trusted LAN; stop after use.')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    if not (ROOT / 'index.html').is_file():
        sys.exit('index.html is missing. Run python tools/build.py first.')
    host = '0.0.0.0' if args.lan else '127.0.0.1'
    try:
        server = ThreadingHTTPServer((host, args.port), partial(Handler, directory=str(ROOT)))
    except OSError as error:
        sys.exit(f'Cannot listen on {host}:{args.port}: {error}. Try --port 8766.')
    url = f'http://127.0.0.1:{args.port}/index.html'
    print(f'Open: {url}\nPress Ctrl+C to stop.')
    if args.lan:
        print('LAN mode: anyone on an allowed network can read files in this project folder.\n'
              'Only use a trusted private network. Do not port-forward this service.\n'
              f'Phone: http://YOUR_COMPUTER_LAN_IP:{args.port}/index.html')
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        server.server_close()
