"""Loopback-only HTTP server for the packaged read-only observer."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .core import load_state


WEB_FILE = Path(__file__).with_name("web") / "index.tmpl"


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True


def make_server(project: str | Path, feature: str, port: int = 4177) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, content_type: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            route = urlparse(self.path).path
            if route == "/":
                try:
                    payload = WEB_FILE.read_bytes()
                except OSError as exc:
                    self._send(500, "text/plain; charset=utf-8", str(exc).encode("utf-8"))
                    return
                self._send(200, "text/html; charset=utf-8", payload)
                return
            if route == "/api/state":
                state = load_state(project, feature)
                payload = json.dumps(state, ensure_ascii=False).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", payload)
                return
            if route == "/healthz":
                payload = json.dumps({"ok": True, "service": "agent-ticket-tracker"}).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", payload)
                return
            self._send(404, "text/plain; charset=utf-8", b"Not found\n")

        def log_message(self, format: str, *args: object) -> None:
            return

    return _Server(("127.0.0.1", port), Handler)


def serve(project: str | Path, feature: str, port: int) -> int:
    server = make_server(project, feature, port)
    host, actual_port = server.server_address
    print(f"url=http://localhost:{actual_port}/")
    print("mode=loopback-read-only")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        server.server_close()
    return 0
