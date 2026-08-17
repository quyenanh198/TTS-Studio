"""Per-session error log: API errors, client-reported errors and logger warnings all land in it."""

import logging

from fastapi.testclient import TestClient

from app import errlog
from app.main import app


def _read() -> str:
    p = errlog.session_log_path()
    assert p is not None and p.exists()
    for h in logging.getLogger().handlers:
        h.flush()
    return p.read_text(encoding="utf-8")


def test_session_log_created_with_header():
    txt = _read()
    assert txt.startswith("# TTS Studio")
    assert "session error log" in txt


def test_http_and_client_errors_are_logged():
    c = TestClient(app)
    r = c.post("/api/tts/synthesize", json={"chapters": []})  # 422 validation error
    assert r.status_code == 422
    r = c.post("/api/system/client-error", json={"message": "Boom from UI", "stack": "at x.tsx:1", "source": "toast", "url": "#/tts"})
    assert r.status_code == 200
    r = c.post("/api/system/open", json={"path": "Z:/does/not/exist"})  # 404 is intentionally NOT logged
    assert r.status_code == 404
    logging.getLogger("test").warning("plain warning %d", 42)
    txt = _read()
    assert "POST /api/tts/synthesize -> 422" in txt
    assert "client: toast: Boom from UI  [#/tts]" in txt and "at x.tsx:1" in txt
    assert "plain warning 42" in txt
    assert "/api/system/open -> 404" not in txt


def test_system_info_exposes_log_paths():
    info = TestClient(app).get("/api/system").json()
    assert info["session_log"] == str(errlog.session_log_path())
    assert info["logs_dir"].endswith("logs")
