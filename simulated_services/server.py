"""
Minimal, dependency-free HTTP stub used to simulate a legacy service's
health endpoint for Phase 5 Docker Compose demonstrations.

Configured entirely through environment variables so the same image is
reused for every simulated service in docker-compose.yml:

  PORT          - port to listen on (default 8080)
  HEALTH_PATH   - path that returns 200 (default /health)
  SERVICE_NAME  - name reported in the health response body

Every other path returns 404. This intentionally does nothing beyond
that: it exists only to give Phase 2B's real HealthCheckService something
real to probe over HTTP within the Compose network, matching the
host/port/health_endpoint already declared in config/services.yaml. It
does not simulate any actual service (auth/db/cache/queue) behavior.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))
HEALTH_PATH = os.environ.get("HEALTH_PATH", "/health")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "simulated-service")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == HEALTH_PATH:
            body = json.dumps({"status": "healthy", "service": SERVICE_NAME}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, log_format, *args):
        print(f"[{SERVICE_NAME}] {self.address_string()} - {log_format % args}", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"[{SERVICE_NAME}] listening on 0.0.0.0:{PORT}, health path {HEALTH_PATH}", flush=True)
    server.serve_forever()
