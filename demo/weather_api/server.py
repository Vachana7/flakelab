"""A small fake weather service used by the ShopLite demo.

It runs in its own container so the demo works without internet (useful at
an expo). Like many real services, it is occasionally slow: with probability
SLOW_PROBABILITY it waits SLOW_SECONDS before answering.
"""

import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SLOW_PROBABILITY = float(os.environ.get("SLOW_PROBABILITY", "0.1"))
SLOW_SECONDS = float(os.environ.get("SLOW_SECONDS", "1.5"))
PORT = int(os.environ.get("PORT", "8000"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        city = parse_qs(url.query).get("city", ["Mysuru"])[0]
        if url.path == "/health":
            body = {"status": "ok"}
        elif url.path == "/forecast":
            body = {"city": city, "rain_mm": round(random.uniform(0, 25), 1)}
        elif url.path == "/alerts":
            body = {"city": city, "alerts": random.choice([[], ["heavy rain"]])}
        else:
            self.send_response(404)
            self.end_headers()
            return
        if url.path != "/health" and random.random() < SLOW_PROBABILITY:
            time.sleep(SLOW_SECONDS)
        data = json.dumps(body).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            # Expected: this was a deliberately slow reply, and the client had
            # already given up (its timeout is shorter). That is the planted flakiness.
            print(f"slow reply to {url.path} arrived after the client's timeout (expected)")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"weather-api listening on :{PORT} (slow {SLOW_PROBABILITY:.0%} of requests)")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
