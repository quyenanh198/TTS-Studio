"""SQLite persistence for job history and voice profiles."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    params TEXT NOT NULL DEFAULT '{}',
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS voice_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    gender TEXT NOT NULL DEFAULT 'female',
    language TEXT NOT NULL DEFAULT 'vi',
    ref_path TEXT NOT NULL,
    engine TEXT NOT NULL DEFAULT 'seedvc',
    base_voice TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    # ---- jobs -------------------------------------------------------------
    def insert_job(self, job_id: str, kind: str, params: dict[str, Any]) -> None:
        now = utcnow()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO jobs(id,kind,status,progress,message,params,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (job_id, kind, "queued", 0.0, "", json.dumps(params, ensure_ascii=False), now, now),
            )

    def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        if "result" in fields and fields["result"] is not None:
            fields["result"] = json.dumps(fields["result"], ensure_ascii=False)
        fields["updated_at"] = utcnow()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id)
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(self, limit: int = 100, kind: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM jobs"
        args: tuple[Any, ...] = ()
        if kind:
            q += " WHERE kind=?"
            args = (kind,)
        q += " ORDER BY created_at DESC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(q, (*args, limit)).fetchall()
        return [self._row_to_job(r) for r in rows]

    def fail_orphaned_jobs(self, message: str) -> int:
        """Jobs left queued/running by a previous process can never finish — mark them failed."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE jobs SET status='error', message=?, updated_at=? WHERE status IN ('queued','running')",
                (message, utcnow()),
            )
            return cur.rowcount

    def delete_job(self, job_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["params"] = json.loads(d.get("params") or "{}")
        d["result"] = json.loads(d["result"]) if d.get("result") else None
        return d

    # ---- voice profiles ---------------------------------------------------
    def insert_profile(self, profile: dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO voice_profiles(id,name,gender,language,ref_path,engine,base_voice,notes,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    profile["id"],
                    profile["name"],
                    profile.get("gender", "female"),
                    profile.get("language", "vi"),
                    profile["ref_path"],
                    profile.get("engine", "seedvc"),
                    profile.get("base_voice"),
                    profile.get("notes", ""),
                    utcnow(),
                ),
            )

    def update_profile(self, profile_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE voice_profiles SET {cols} WHERE id=?", (*fields.values(), profile_id)
            )

    def list_profiles(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM voice_profiles ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM voice_profiles WHERE id=?", (profile_id,)
            ).fetchone()
        return dict(row) if row else None

    def delete_profile(self, profile_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM voice_profiles WHERE id=?", (profile_id,))


db = Database()
