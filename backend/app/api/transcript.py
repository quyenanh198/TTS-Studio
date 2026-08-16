"""Transcript (ASR) endpoints."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..config import CACHE_DIR, settings
from ..jobs import JobContext, jobs
from ..services import asr, ffmpeg
from ..services.srt import Cue
from ..services.text import safe_filename

router = APIRouter()
MEDIA_DIR = CACHE_DIR / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

MEDIA_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".mp4", ".mkv", ".mov",
             ".webm", ".avi", ".ts", ".m4b"}


@router.post("/transcript/upload")
async def upload_media(file: UploadFile = File(...)) -> dict[str, Any]:
    name = Path(file.filename or "media").name
    ext = Path(name).suffix.lower()
    if ext not in MEDIA_EXT:
        raise HTTPException(415, f"Định dạng không hỗ trợ: {ext}")
    dest = MEDIA_DIR / f"{int(time.time())}_{safe_filename(Path(name).stem)}{ext}"
    with open(dest, "wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)
    dur = ffmpeg.probe_duration(dest) if ffmpeg.is_available() else 0.0
    return {"path": str(dest), "name": name, "duration": round(dur, 2)}


class TranscribeBody(BaseModel):
    path: str
    model: str = "small"
    language: str | None = None
    device: str = "auto"
    separate_vocals: bool = False
    word_timestamps: bool = True
    formats: list[str] = ["srt"]
    initial_prompt: str | None = None


@router.post("/transcript")
def transcribe(body: TranscribeBody) -> dict[str, Any]:
    media = Path(body.path)
    if not media.is_file():
        raise HTTPException(404, "Không tìm thấy file media")
    if not asr.is_downloaded(body.model):
        raise HTTPException(409, f"Model {body.model} chưa tải")

    def job(ctx: JobContext) -> dict[str, Any]:
        return asr.transcribe(ctx, media, model=body.model, language=body.language,
                              device=body.device or settings.get("asr_device", "auto"),
                              word_timestamps=body.word_timestamps, separate=body.separate_vocals,
                              formats=body.formats, initial_prompt=body.initial_prompt)

    params = body.model_dump()
    params["title"] = media.name
    return jobs.submit("transcript", params, job)


@router.get("/transcript/models")
def list_models() -> list[dict[str, Any]]:
    return asr.list_models()


class ModelBody(BaseModel):
    name: str


@router.post("/transcript/models/download")
def download_model(body: ModelBody) -> dict[str, Any]:
    if body.name not in {m["name"] for m in asr.MODELS}:
        raise HTTPException(422, "Model không hợp lệ")

    def job(ctx: JobContext) -> dict[str, Any]:
        return {"path": str(asr.download_model(body.name, ctx.progress))}

    return jobs.submit("asr_model", {"name": body.name, "title": f"Model {body.name}"}, job)


@router.get("/transcript/gpu")
def gpu_status() -> dict[str, Any]:
    return {"cuda": asr.cuda_available(), "libs_installed": asr.gpu_support_installed(),
            "demucs": asr.demucs_available()}


@router.post("/transcript/gpu/install")
def gpu_install() -> dict[str, Any]:
    def job(ctx: JobContext) -> dict[str, Any]:
        asr.install_gpu_support(ctx.progress)
        return {"ok": True}

    return jobs.submit("gpu_install", {"title": "Cài GPU (cuBLAS/cuDNN)"}, job)


class ExportBody(BaseModel):
    cues: list[dict[str, Any]]
    formats: list[str] = ["srt"]
    stem: str = "transcript"
    out_dir: str | None = None
    title: str = ""


@router.post("/transcript/export")
def export_cues(body: ExportBody) -> dict[str, Any]:
    cues = [Cue(float(c["start"]), float(c["end"]), str(c["text"]), i + 1) for i, c in enumerate(body.cues)]
    out_dir = Path(body.out_dir) if body.out_dir else settings.output_dir / "transcripts"
    outputs = asr.write_outputs(cues, out_dir, safe_filename(body.stem), body.formats, body.title)
    return {"out_dir": str(out_dir), "outputs": outputs}
