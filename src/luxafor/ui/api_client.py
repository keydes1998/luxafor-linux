"""REST client for the GUI core + threaded call helpers."""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from urllib.error import HTTPError, URLError

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


def api_base() -> str:
    base = os.environ.get("LUXAFOR_API", "")
    if base:
        return base
    try:
        cfg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        with open(os.path.join(cfg, "luxafor", "api-endpoint")) as fh:
            val = fh.read().strip()
            if val:
                return val
    except OSError:
        pass
    return "http://127.0.0.1:17800"


def call(method: str, path: str, payload: dict | None = None, timeout: float = 8) -> dict | list:
    url = api_base() + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except HTTPError as exc:
        try:
            return json.loads(exc.read().decode())
        except Exception:
            return {"error": f"HTTP {exc.code}"}
    except (URLError, OSError, TimeoutError) as exc:
        return {"error": f"core-unreachable: {exc}", "_unreachable": True}


def core_running(timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(api_base() + "/api/health", timeout=timeout):
            return True
    except Exception:
        return False


def ensure_core() -> bool:
    """Starts the core daemon if it is not running. Prefers the systemd user
    service (no orphan processes); spawning is only a last resort."""
    if core_running():
        return True
    import shutil
    systemctl = shutil.which("systemctl")
    if systemctl:
        env = {**os.environ, "XDG_RUNTIME_DIR": os.environ.get(
            "XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")}
        try:
            subprocess.run([systemctl, "--user", "start", "luxafor-core.service"],
                           env=env, timeout=15, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for _ in range(20):
            time.sleep(0.5)
            if core_running(timeout=1.0):
                return True
    exe = shutil.which("lx-core")
    if exe:
        subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    else:
        import sys
        subprocess.Popen([sys.executable, "-m", "luxafor", "core"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    for _ in range(40):
        time.sleep(0.25)
        if core_running(timeout=1.0):
            return True
    return False


class WorkerSignals(QObject):
    done = Signal(object)


class HttpWorker(QRunnable):
    """Runs an API call in the thread pool and emits the parsed result."""

    def __init__(self, fn) -> None:
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            res = self.fn()
        except Exception as exc:  # never crash the GUI thread
            res = {"error": str(exc)}
        try:
            self.signals.done.emit(res)
        except RuntimeError:
            pass  # receiver (page) already deleted during shutdown


def run_async(fn, on_done) -> None:
    """fn: zero-arg callable returning JSON-ish data; on_done called on the
    GUI thread with the result."""
    worker = HttpWorker(fn)
    worker.signals.done.connect(on_done)
    QThreadPool.globalInstance().start(worker)