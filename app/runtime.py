"""Runtime helpers shared by the dev entry point and the packaged app."""

from __future__ import annotations

import json
import os
import socket
import tempfile
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_PORT = 8765

# /api/app-info 返回的应用标识，用于把本应用的实例和无关进程区分开
INSTANCE_MARKER = "calculator-toolkit"

# 本机探测必须绕过系统代理（HTTP_PROXY 等对 loopback 的转发不可靠）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

_LOCK_PATH = Path(tempfile.gettempdir()) / "calculator-toolkit-instance.lock"


def _port_available(port: int) -> bool:
    """A port counts as available when we can bind it on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def pick_free_port(preferred: int = DEFAULT_PORT, attempts: int = 31) -> int:
    """Return a usable port, preferring the default one.

    Scans upward from ``preferred`` so the documented URL stays stable unless
    the port is really taken; when the whole range is busy, falls back to an
    OS-assigned ephemeral port. The probe releases the socket before uvicorn
    binds it, which leaves a tiny race window — acceptable for a local tool.
    """
    for port in range(preferred, preferred + attempts):
        if _port_available(port):
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def find_running_instance(preferred: int = DEFAULT_PORT, attempts: int = 31) -> int | None:
    """Return the port of an already-running instance, or None.

    Probes the same port range ``pick_free_port`` uses and identifies our app
    via ``/api/app-info``, so unrelated services (e.g. another project's dev
    server) are not mistaken for an instance. Loopback connection refusals are
    instant, so the scan costs little; only occupied-but-slow ports may pay a
    probe timeout each.
    """
    for port in range(preferred, preferred + attempts):
        try:
            with _OPENER.open(f"http://127.0.0.1:{port}/api/app-info", timeout=0.5) as resp:
                if json.load(resp).get("app") == INSTANCE_MARKER:
                    return port
        except (OSError, ValueError):
            continue
    return None


def wait_for_running_instance(timeout: float = 20.0, interval: float = 0.4) -> int | None:
    """Wait for an instance that holds the lock but is still booting to serve.

    Booting takes a few seconds (interpreter start, imports, uvicorn bind), so
    a launcher that lost the lock race polls instead of giving up at once.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        port = find_running_instance()
        if port is not None:
            return port
        time.sleep(interval)
    return None


@contextmanager
def single_instance_lock(path: Path | None = None) -> Iterator[bool]:
    """Cross-platform single-instance gate; yields True when the lock is ours.

    The lock is held for the whole ``with`` block, so the caller must keep the
    server running inside it. It is released on close or process exit, and the
    OS drops it automatically if the process dies — no stale locks. Windows
    uses ``msvcrt.locking``, POSIX uses ``fcntl.flock``.
    """
    fd = os.open(str(path or _LOCK_PATH), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
        else:
            yield True
    finally:
        os.close(fd)
