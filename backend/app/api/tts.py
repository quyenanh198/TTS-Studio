"""TTS endpoints: voice catalog, preview, synthesize job."""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import CACHE_DIR
from ..jobs import JobContext, jobs
from ..services import tts_engine, voices

router = APIRouter()
PREVIEW_DIR = CACHE_DIR / "previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/voices")
def list_voices(refresh: bool = False) -> list[dict[str, Any]]:
    return voices.all_voices(force=refresh)


class PreviewBody(BaseModel):
    voice: str
    text: str | None = None


@router.post("/voices/preview")
def preview_voice(body: PreviewBody) -> dict[str, str]:
    key = hashlib.sha1(f"{body.voice}|{body.text or ''}".encode()).hexdigest()[:16]
    out = PREVIEW_DIR / f"{key}.mp3"
    if not out.exists():
        try:
            tts_engine.preview(body.voice, body.text, out)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, str(exc)) from exc
    from urllib.parse import quote

    return {"path": str(out), "url": f"/api/system/file?path={quote(str(out))}"}


@router.post("/tts/synthesize")
def synthesize(body: dict[str, Any]) -> dict[str, Any]:
    try:
        req = tts_engine.TtsRequest.from_dict(body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Yêu cầu không hợp lệ: {exc}") from exc
    if not req.chapters or not any((c.text or "").strip() or c.cues for c in req.chapters):
        raise HTTPException(422, "Không có nội dung")

    def job(ctx: JobContext) -> dict[str, Any]:
        return tts_engine.run_tts(ctx, req)

    params = {k: v for k, v in body.items() if k != "chapters"}
    params["title"] = req.title
    params["chapters_count"] = len(req.chapters)
    params["chars"] = sum(len(c.text or "") for c in req.chapters)
    return jobs.submit("tts", params, job)
