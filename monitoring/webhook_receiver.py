from http.server import BaseHTTPRequestHandler, HTTPServer
import sys

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('content-length', 0))
        body = self.rfile.read(length).decode('utf-8', errors='replace')
        print("=== REQUEST RECEIVED ===", file=sys.stderr)
        print(f"Path: {self.path}", file=sys.stderr)
        print(self.headers, file=sys.stderr)
        print(body, file=sys.stderr)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')

    def log_message(self, format, *args):
        # Silence default logging to stdout (optional)
        return

if __name__ == "__main__":
    port = 9000
    print(f"Listening on 0.0.0.0:{port}", file=sys.stderr)
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
