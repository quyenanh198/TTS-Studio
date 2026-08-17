"""Per-session error log.

Every app run gets its own file `<data>/logs/errors/session-YYYYmmdd-HHMMSS-<pid>.log` collecting *all*
errors of that session in one place: backend WARNING/ERROR records with tracebacks (jobs, API 4xx/5xx,
uncaught exceptions in any thread) and errors reported by the UI (toasts, window.onerror, unhandled
promise rejections). `logs/app.log` remains the full rotating log; this file is the one to send when
something went wrong.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
import threading
import time
import traceback
from pathlib import Path

from .config import DATA_DIR

ERRORS_DIR = DATA_DIR / "logs" / "errors"
KEEP_SESSIONS = 30
_FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

_lock = threading.Lock()
_path: Path | None = None
_client_log = logging.getLogger("client")  # UI-reported errors


def session_log_path() -> Path | None:
    return _path


def setup(app_version: str = "") -> Path | None:
    """Create the session file + attach a WARNING-level handler to the root logger. Idempotent."""
    global _path
    with _lock:
        if _path is not None:
            return _path
        try:
            ERRORS_DIR.mkdir(parents=True, exist_ok=True)
            path = ERRORS_DIR / f"session-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.log"
            handler = logging.FileHandler(path, encoding="utf-8")
            handler.setLevel(logging.WARNING)
            handler.setFormatter(logging.Formatter(_FMT))
            root = logging.getLogger()
            root.addHandler(handler)
            if root.level > logging.WARNING or root.level == logging.NOTSET:
                root.setLevel(logging.INFO)
            _path = path
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"# TTS Studio {app_version} — session error log\n"
                        f"# {time.strftime('%Y-%m-%d %H:%M:%S')} | {platform.platform()} | Python {sys.version.split()[0]}"
                        f" | pid {os.getpid()}\n# Chỉ ghi WARNING/ERROR. Log đầy đủ: logs/app.log\n")
            _install_hooks()
            _prune()
        except Exception as exc:  # noqa: BLE001 — logging must never break the app
            logging.getLogger(__name__).warning("session error log disabled: %s", exc)
            _path = None
        return _path


def _install_hooks() -> None:
    """Uncaught exceptions on the main thread and in worker threads → log (then default behaviour)."""
    log = logging.getLogger("uncaught")
    prev_hook = sys.excepthook

    def excepthook(t, v, tb):  # noqa: ANN001
        log.error("uncaught exception: %s", "".join(traceback.format_exception(t, v, tb)))
        prev_hook(t, v, tb)

    sys.excepthook = excepthook
    prev_thread_hook = threading.excepthook

    def thread_hook(args):  # noqa: ANN001
        log.error("uncaught exception in thread %s: %s", args.thread.name if args.thread else "?",
                  "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
        prev_thread_hook(args)

    threading.excepthook = thread_hook


def _prune() -> None:
    files = sorted(ERRORS_DIR.glob("session-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[KEEP_SESSIONS:]:
        try:
            old.unlink()
        except OSError:
            pass


def log_client_error(message: str, stack: str = "", source: str = "", url: str = "") -> None:
    """Error reported by the frontend (toast / window.onerror / unhandledrejection)."""
    detail = message.strip()
    if url:
        detail += f"  [{url}]"
    if stack.strip():
        detail += "\n" + stack.strip()
    _client_log.error("%s%s", f"{source}: " if source else "", detail)


def log_http_error(method: str, path: str, status: int, detail: object) -> None:
    logging.getLogger("http").warning("%s %s -> %s: %s", method, path, status, detail)
