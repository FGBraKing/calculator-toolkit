"""Entry point for the packaged single-file app."""

from __future__ import annotations

import os
import threading
import time
import webbrowser

os.environ["CALC_TOOLKIT_APP"] = "1"

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402

URL = "http://127.0.0.1:8765"


def _open_browser() -> None:
    time.sleep(1.2)
    webbrowser.open(URL)


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
