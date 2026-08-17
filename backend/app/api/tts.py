"""TTS endpoints: voice catalog, preview, synthesize job."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

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


class CueIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(min_length=1, max_length=2000)


class ChapterBody(BaseModel):
    title: str = Field(default="Chương", max_length=200)
    text: str = Field(default="", max_length=2_000_000)
    cues: list[CueIn] | None = None


class SynthesizeBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(default="Audio", max_length=200)
    chapters: list[ChapterBody] = Field(min_length=1, max_length=2000)
    voice: str = Field(default="vi-VN-HoaiMyNeural", min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_:\-]+$")
    rate: float = Field(default=1.0, ge=0.5, le=2.0)
    volume: float = Field(default=1.0, ge=0.2, le=2.0)
    keep_pitch: bool = True
    pitch: float = Field(default=0.0, ge=-12, le=12)
    format: Literal["mp3", "wav"] = "mp3"
    export_mode: Literal["per_chapter", "merged", "range", "per_cue"] = "per_chapter"
    range_start: int | None = Field(default=None, ge=1)
    range_end: int | None = Field(default=None, ge=1)
    merge_every: int | None = Field(default=None, ge=0, le=1000)
    make_srt: bool = True
    make_zip: bool = False
    make_m4b: bool = False
    clone_profile: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9]+$")
    output_dir: str | None = None
    gap_ms: int = Field(default=700, ge=0, le=10_000)
    expressive: bool = False
    expressive_level: float = Field(default=0.7, ge=0.0, le=1.0)


@router.post("/tts/synthesize")
def synthesize(body: SynthesizeBody) -> dict[str, Any]:
    if body.output_dir is not None:
        p = Path(body.output_dir)
        if not p.is_absolute():
            raise HTTPException(422, "output_dir phải là đường dẫn tuyệt đối")
    if body.range_start and body.range_end and body.range_end < body.range_start:
        raise HTTPException(422, "range_end phải ≥ range_start")
    req = tts_engine.TtsRequest.from_dict(body.model_dump())
    if not any((c.text or "").strip() or c.cues for c in req.chapters):
        raise HTTPException(422, "Không có nội dung")

    def job(ctx: JobContext) -> dict[str, Any]:
        return tts_engine.run_tts(ctx, req)

    params = body.model_dump(exclude={"chapters"})
    params["chapters_count"] = len(req.chapters)
    params["chars"] = sum(len(c.text or "") for c in req.chapters)
    return jobs.submit("tts", params, job)
