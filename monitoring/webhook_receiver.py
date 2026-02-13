#!/usr/bin/env python3
"""
Simple webhook receiver that:
 - accepts POST deliveries (any path)
 - increments a Prometheus counter for each delivery
 - serves Prometheus metrics on GET /metrics (text exposition)
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import sys
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

# Prometheus metric
DELIVERY_COUNTER = Counter(
    'alertmanager_webhook_deliveries_total',
    'Number of Alertmanager webhook deliveries received'
)

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0) or 0)
        body = self.rfile.read(length) if length else b''
        try:
            payload = json.loads(body.decode('utf-8')) if body else None
        except Exception:
            payload = body.decode('utf-8', errors='replace')
        print(f"Received webhook on {self.path}: {payload}")
        # increment prometheus counter
        DELIVERY_COUNTER.inc()
        # respond 200
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_GET(self):
        if self.path == '/metrics':
            # return prometheus text format
            data = generate_latest()
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            # preserve previous behaviour: indicate unsupported method/path
            self.send_response(501)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(b"<html><body><h1>501 Unsupported</h1></body></html>")

    def log_message(self, format, *args):
        # print to stdout
        print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))

def run(addr='0.0.0.0', port=9000):
    server = HTTPServer((addr, port), Handler)
    print(f"Listening on {addr}:{port} (webhook POSTs and /metrics)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down", file=sys.stderr)
        server.server_close()

if __name__ == '__main__':
    run()
