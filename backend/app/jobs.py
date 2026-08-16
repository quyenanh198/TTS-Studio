"""Background job manager.

Jobs run in a thread pool (most work is blocking: ffmpeg, torch, whisper).
Progress is persisted to SQLite and broadcast to websocket subscribers.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from .db import db

log = logging.getLogger(__name__)

JobFn = Callable[["JobContext"], Any]


class JobCancelled(Exception):
    pass


@dataclass
class JobContext:
    id: str
    kind: str
    params: dict[str, Any]
    _manager: "JobManager"
    _cancel: threading.Event = field(default_factory=threading.Event)

    def progress(self, value: float, message: str = "") -> None:
        self.check_cancelled()
        self._manager._update(self.id, progress=max(0.0, min(1.0, value)), message=message)

    def check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise JobCancelled()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()


class JobManager:
    def __init__(self, workers: int = 2):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self._contexts: dict[str, JobContext] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ---- submission --------------------------------------------------------
    def submit(self, kind: str, params: dict[str, Any], fn: JobFn) -> dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        db.insert_job(job_id, kind, params)
        ctx = JobContext(id=job_id, kind=kind, params=params, _manager=self)
        with self._lock:
            self._contexts[job_id] = ctx
        self._broadcast(db.get_job(job_id))
        self._pool.submit(self._run, ctx, fn)
        return db.get_job(job_id)  # type: ignore[return-value]

    def _run(self, ctx: JobContext, fn: JobFn) -> None:
        if ctx.cancelled:  # cancelled while still queued
            self._update(ctx.id, status="cancelled", message="Đã hủy")
            with self._lock:
                self._contexts.pop(ctx.id, None)
            return
        self._update(ctx.id, status="running", message="Đang xử lý...")
        try:
            result = fn(ctx)
            self._update(ctx.id, status="done", progress=1.0, message="Hoàn tất", result=result)
        except JobCancelled:
            self._update(ctx.id, status="cancelled", message="Đã hủy")
        except Exception as exc:  # noqa: BLE001
            log.error("job %s failed: %s\n%s", ctx.id, exc, traceback.format_exc())
            self._update(ctx.id, status="error", message=str(exc), error=traceback.format_exc())
        finally:
            with self._lock:
                self._contexts.pop(ctx.id, None)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            ctx = self._contexts.get(job_id)
        if ctx is None:
            job = db.get_job(job_id)
            if job and job["status"] == "queued":
                self._update(job_id, status="cancelled", message="Đã hủy")
                return True
            return False
        ctx._cancel.set()
        return True

    # ---- state -------------------------------------------------------------
    def _update(self, job_id: str, **fields: Any) -> None:
        db.update_job(job_id, **fields)
        self._broadcast(db.get_job(job_id))

    def _broadcast(self, job: dict[str, Any] | None) -> None:
        if job is None or self._loop is None:
            return
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                self._loop.call_soon_threadsafe(self._offer, q, job)
            except RuntimeError:
                pass

    @staticmethod
    def _offer(q: asyncio.Queue, job: dict[str, Any]) -> None:
        try:
            q.put_nowait(job)
        except asyncio.QueueFull:
            # slow consumer: drop the oldest event rather than raising inside the loop callback
            try:
                q.get_nowait()
                q.put_nowait(job)
            except Exception:  # noqa: BLE001
                pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def shutdown(self) -> None:
        """Best-effort stop for process exit: flag every running job, drop queued ones."""
        with self._lock:
            ctxs = list(self._contexts.values())
        for c in ctxs:
            c._cancel.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def get(self, job_id: str) -> dict[str, Any] | None:
        return db.get_job(job_id)

    def list(self, limit: int = 100, kind: str | None = None) -> list[dict[str, Any]]:
        return db.list_jobs(limit=limit, kind=kind)

    def delete(self, job_id: str) -> None:
        self.cancel(job_id)
        db.delete_job(job_id)


def _workers() -> int:
    try:
        from .config import settings

        return max(1, min(8, int(settings.get("concurrency", 2) or 2)))
    except Exception:
        return 2


jobs = JobManager(workers=_workers())
