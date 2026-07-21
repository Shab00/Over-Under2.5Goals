#!/usr/bin/env python3
"""
Alertmanager webhook receiver that:
- increments a Prometheus counter for each delivery
- forwards the alert to a Telegram channel
- serves Prometheus metrics on GET /metrics
Uses ONLY Python standard library.
"""
import os
import json
import sys
import time
import argparse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

class ReceiverHandler(BaseHTTPRequestHandler):
    deliveries = 0
    created_ts = int(time.time())
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''
        try:
            data = json.loads(body.decode('utf-8'))
        except Exception:
            data = None

        # Increment counter
        ReceiverHandler.deliveries += 1

        # Forward to Telegram if possible
        if self.token and self.chat_id and data:
            self.send_telegram_alert(data)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def send_telegram_alert(self, data):
        """Build and send a formatted message to Telegram."""
        try:
            lines = ["🚨 Alertmanager notification"]
            for alert in data.get("alerts", []):
                status = alert.get("status", "unknown").upper()
                name = alert.get("labels", {}).get("alertname", "No name")
                summary = alert.get("annotations", {}).get("summary", "")
                lines.append(f"\n{name} ({status})")
                if summary:
                    lines.append(summary)
            text = "\n".join(lines)

            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = json.dumps({
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(f"Telegram message sent, status: {resp.status}")
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")

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
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Webhook receiver is running.\n")

    def log_message(self, fmt, *args):
        # silence default logging
        return

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", "-p", default=9000, type=int)
    args = p.parse_args()
    server = HTTPServer(("0.0.0.0", args.port), ReceiverHandler)
    print(f"Webhook receiver listening on port {args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()

if __name__ == "__main__":
    main()
