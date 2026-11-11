from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from fastapi.testclient import TestClient

from app.main import app
from app.runtime import find_running_instance, pick_free_port

client = TestClient(app)


def _reserve_port() -> tuple[int, socket.socket]:
    """拿到一个确定空闲的端口并占住它，返回 (端口, 占位 socket)。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return int(sock.getsockname()[1]), sock


def test_prefers_the_requested_port_when_free():
    port, blocker = _reserve_port()
    blocker.close()
    assert pick_free_port(preferred=port, attempts=1) == port


def test_skips_occupied_port_and_falls_back():
    port, blocker = _reserve_port()
    try:
        chosen = pick_free_port(preferred=port, attempts=1)
    finally:
        blocker.close()
    assert chosen != port
    assert chosen > 0


def test_app_info_reports_instance_marker():
    assert client.get("/api/app-info").json() == {"app": "calculator-toolkit"}


def test_finds_running_instance_by_marker():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"app": "calculator-toolkit"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert find_running_instance(preferred=port, attempts=1) == port
    finally:
        server.shutdown()


def test_ignores_foreign_services():
    port, blocker = _reserve_port()
    try:
        assert find_running_instance(preferred=port, attempts=1) is None
    finally:
        blocker.close()
