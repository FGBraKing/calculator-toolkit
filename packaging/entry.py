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
from app.runtime import (  # noqa: E402
    find_running_instance,
    pick_free_port,
    single_instance_lock,
    wait_for_running_instance,
)


def _open_browser(port: int) -> None:
    """等端口真正可连接后再打开浏览器，避免打包版首启过慢时打开错误页。"""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    webbrowser.open(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    with single_instance_lock() as acquired:
        if not acquired:
            # 已有实例在运行或正在启动：等它就绪，打开它的页面，本次启动退出
            running = wait_for_running_instance()
            if running is None:
                raise SystemExit(1)
            webbrowser.open(f"http://127.0.0.1:{running}")
            raise SystemExit(0)
        running = find_running_instance()
        if running is not None:
            # 锁空闲但端口段里有实例（如 --port 起的并行实例），直接复用
            webbrowser.open(f"http://127.0.0.1:{running}")
            raise SystemExit(0)
        PORT = pick_free_port()
        threading.Thread(target=_open_browser, args=(PORT,), daemon=True).start()
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
