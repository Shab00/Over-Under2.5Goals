#!/usr/bin/env python3
"""
Optional mock app metrics server exposing basic metrics at /metrics.

Serves a couple of example metrics used by dashboards.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import time
import argparse

START_TS = int(time.time())
REQS = 0

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global REQS
        if self.path == "/metrics":
            REQS += 1
            lines = []
            lines.append('# HELP mock_app_requests_total Total requests to mock app')
            lines.append('# TYPE mock_app_requests_total counter')
            lines.append(f'mock_app_requests_total {REQS}.0')
            lines.append('# HELP mock_app_start_time_seconds Start time of mock app')
            lines.append('# TYPE mock_app_start_time_seconds gauge')
            lines.append(f'mock_app_start_time_seconds {START_TS}.0')
            payload = ("\n".join(lines) + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        return

def run(addr="0.0.0.0", port=8000):
    server = HTTPServer((addr, int(port)), Handler)
    print(f"Mock app metrics listening on {addr}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", "-p", default=8000, type=int)
    args = p.parse_args()
    run(port=args.port)
