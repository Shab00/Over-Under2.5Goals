#!/usr/bin/env python3
"""
Simple mock Alertmanager webhook receiver.

- Accepts POST on any path (increments a counter)
- Serves Prometheus metrics at GET /metrics in plain text exposition
No external dependencies; uses Python stdlib only.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import argparse
import threading
import time

class ReceiverHandler(BaseHTTPRequestHandler):
    deliveries = 0
    created_ts = int(time.time())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(body.decode("utf-8")) if body else None
        except Exception:
            payload = body.decode("utf-8", errors="replace")
        ReceiverHandler.deliveries += 1
        print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ')}] Received webhook {self.path}: {payload}")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_GET(self):
        if self.path == "/metrics":
            # Prometheus text exposition
            lines = []
            lines.append('# HELP alertmanager_webhook_deliveries_total Number of Alertmanager webhook deliveries received')
            lines.append('# TYPE alertmanager_webhook_deliveries_total counter')
            lines.append(f'alertmanager_webhook_deliveries_total {ReceiverHandler.deliveries}.0')
            lines.append('# HELP alertmanager_webhook_deliveries_created Unix start time for receiver (gauge)')
            lines.append('# TYPE alertmanager_webhook_deliveries_created gauge')
            lines.append(f'alertmanager_webhook_deliveries_created {ReceiverHandler.created_ts}.0')
            payload = ("\n".join(lines) + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        # silence default logging to stderr; keep our printed lines
        return

def run(addr="0.0.0.0", port=9000):
    server = HTTPServer((addr, int(port)), ReceiverHandler)
    print(f"Listening for webhook POSTs and /metrics on {addr}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", "-p", default=9000, type=int)
    args = p.parse_args()
    run(port=args.port)
