"""Subprocess helpers: hidden console on Windows, line-streamed progress, cooperative cancel."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
from typing import Callable, Sequence


def hidden_kwargs() -> dict:
    kw: dict = {"stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kw


def run_hidden(cmd: Sequence[str], timeout: float | None = None, check: bool = False) -> subprocess.CompletedProcess:
    """`subprocess.run` that never pops a console window under pythonw and never inherits stdin."""
    return subprocess.run(list(cmd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, check=check, **hidden_kwargs())


def run_streaming(cmd: Sequence[str], on_line: Callable[[str], None] | None = None,
                  should_cancel: Callable[[], bool] | None = None, poll: float = 0.25) -> tuple[int, str]:
    """Run a long command, stream merged stdout/stderr lines to `on_line`, terminate if `should_cancel()`.
    Returns (returncode, last ~4000 chars of output). Raises RuntimeError('cancelled') on cancel."""
    proc = subprocess.Popen(list(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", bufsize=1, **hidden_kwargs())
    tail: list[str] = []
    q: queue.Queue[str | None] = queue.Queue()

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            q.put(line.rstrip("\r\n"))
        q.put(None)

    threading.Thread(target=pump, daemon=True).start()
    try:
        while True:
            if should_cancel and should_cancel():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise RuntimeError("cancelled")
            try:
                item = q.get(timeout=poll)
            except queue.Empty:
                continue
            if item is None:
                break
            tail.append(item)
            if len(tail) > 200:
                del tail[: len(tail) - 200]
            if on_line and item.strip():
                on_line(item)
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
    return proc.returncode or 0, "\n".join(tail)[-4000:]


def wait_cancelable(seconds: float, should_cancel: Callable[[], bool] | None = None, step: float = 0.2) -> None:
    """Sleep in small steps so retries can be interrupted by cancellation."""
    end = time.time() + seconds
    while time.time() < end:
        if should_cancel and should_cancel():
            raise RuntimeError("cancelled")
        time.sleep(min(step, max(0.0, end - time.time())))
