"""API guard tests: file-serving allow-list, SPA path escape, settings + synthesize validation."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import core
from app.config import DATA_DIR
from app.main import app

client = TestClient(app)


def test_is_within_rejects_sibling_prefix(tmp_path: Path):
    root = tmp_path / "TTSStudio"
    root.mkdir()
    sibling = tmp_path / "TTSStudio2"
    sibling.mkdir()
    assert core._is_within(root / "a.mp3", root)
    assert not core._is_within(sibling / "a.mp3", root)
    assert not core._is_within(root / ".." / "x", root)


def test_serve_file_outside_data_dir_forbidden(tmp_path: Path):
    outside = tmp_path / "secret.txt"
    outside.write_text("x")
    r = client.get("/api/system/file", params={"path": str(outside)})
    assert r.status_code == 403


def test_serve_file_inside_data_dir_ok():
    p = DATA_DIR / "probe.txt"
    p.write_text("hello", encoding="utf-8")
    r = client.get("/api/system/file", params={"path": str(p)})
    assert r.status_code == 200 and r.text == "hello"


def test_settings_masks_tiktok_and_validates():
    r = client.put("/api/settings", json={"tiktok_session_id": "abc123", "concurrency": 3})
    assert r.status_code == 200
    assert r.json()["tiktok_session_id"] == core._TIKTOK_MASK
    # sending the mask back keeps the secret
    from app.config import settings

    client.put("/api/settings", json={"tiktok_session_id": core._TIKTOK_MASK})
    assert settings.get("tiktok_session_id") == "abc123"
    assert client.put("/api/settings", json={"concurrency": 99}).status_code == 422
    assert client.put("/api/settings", json={"output_dir": "relative/dir"}).status_code == 422
    assert client.put("/api/settings", json={"default_format": "ogg"}).status_code == 422


def test_synthesize_rejects_bad_payloads():
    base = {"title": "t", "chapters": [{"title": "c", "text": "hello"}]}
    assert client.post("/api/tts/synthesize", json={**base, "format": "mp3/../x"}).status_code == 422
    assert client.post("/api/tts/synthesize", json={**base, "rate": "fast"}).status_code == 422
    assert client.post("/api/tts/synthesize", json={**base, "rate": 9}).status_code == 422
    assert client.post("/api/tts/synthesize", json={**base, "export_mode": "weird"}).status_code == 422
    assert client.post("/api/tts/synthesize", json={**base, "chapters": [{"title": "c", "text": "  "}]}).status_code == 422
    assert client.post("/api/tts/synthesize", json={**base, "voice": "vi-VN-X; rm -rf"}).status_code == 422
