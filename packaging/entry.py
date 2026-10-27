"""Entry point for the packaged single-file app."""

from __future__ import annotations

import os
import socket
import threading
import time
import webbrowser

os.environ["CALC_TOOLKIT_APP"] = "1"

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402

URL = "http://127.0.0.1:8765"


def _open_browser() -> None:
    """等端口真正可连接后再打开浏览器，避免打包版首启过慢时打开错误页。"""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 8765), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    webbrowser.open(URL)


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
