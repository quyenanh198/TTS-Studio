"""Voice clone endpoints: engine status/install, voice profiles, per-language previews."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..config import CACHE_DIR
from ..db import db
from ..jobs import JobContext, jobs
from ..services import clone, ffmpeg
from ..services.text import safe_filename

router = APIRouter()
UPLOAD_DIR = CACHE_DIR / "clone_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/clone/status")
def clone_status() -> dict[str, Any]:
    return clone.status()


@router.post("/clone/install")
def clone_install() -> dict[str, Any]:
    active = [j for j in jobs.list(kind="clone_install", limit=5) if j["status"] in ("queued", "running")]
    if active:
        return active[0]

    def job(ctx: JobContext) -> dict[str, Any]:
        clone.install(ctx.progress, should_cancel=lambda: ctx.cancelled)
        return clone.status()

    return jobs.submit("clone_install", {"title": "Cài đặt Clone giọng (PyTorch + Seed-VC)"}, job)


@router.get("/clone/profiles")
def list_profiles() -> list[dict[str, Any]]:
    return db.list_profiles()


@router.post("/clone/profiles")
async def create_profile(
    name: str = Form(...),
    gender: str = Form("female"),
    language: str = Form("vi"),
    notes: str = Form(""),
    base_voice: str | None = Form(None),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if not ffmpeg.is_available():
        raise HTTPException(409, "FFmpeg chưa được cài (Cài đặt → Tải FFmpeg)")
    ext = Path(file.filename or "ref.wav").suffix.lower() or ".wav"
    dest = UPLOAD_DIR / f"{int(time.time())}_{safe_filename(Path(file.filename or 'ref').stem)}{ext}"
    with open(dest, "wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)
    try:
        # ffmpeg loudnorm etc. is blocking — keep it off the event loop
        return await run_in_threadpool(clone.create_profile, name, gender, language, dest, notes, base_voice or None)
    except RuntimeError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        dest.unlink(missing_ok=True)


class ProfilePatch(BaseModel):
    name: str | None = None
    gender: str | None = None
    language: str | None = None
    base_voice: str | None = None
    notes: str | None = None


@router.patch("/clone/profiles/{pid}")
def patch_profile(pid: str, body: ProfilePatch) -> dict[str, Any]:
    if not db.get_profile(pid):
        raise HTTPException(404, "Profile không tồn tại")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    db.update_profile(pid, **fields)
    return db.get_profile(pid)  # type: ignore[return-value]


@router.delete("/clone/profiles/{pid}")
def delete_profile(pid: str) -> dict[str, bool]:
    clone.delete_profile(pid)
    return {"ok": True}


class PreviewBody(BaseModel):
    lang: str = "vi"


@router.post("/clone/profiles/{pid}/preview")
def preview_profile(pid: str, body: PreviewBody) -> dict[str, Any]:
    profile = db.get_profile(pid)
    if not profile:
        raise HTTPException(404, "Profile không tồn tại")
    if not clone.status()["installed"]:
        raise HTTPException(409, "Chưa cài Clone giọng")

    def job(ctx: JobContext) -> dict[str, Any]:
        p = clone.preview(profile, body.lang, ctx.progress)
        return {"path": str(p), "url": f"/api/system/file?path={quote(str(p))}", "lang": body.lang, "profile": pid}

    return jobs.submit("clone_preview", {"title": f"Nghe thử {profile['name']} ({body.lang})", "profile": pid,
                                          "lang": body.lang}, job)


@router.get("/clone/profiles/{pid}/ref")
def profile_ref_url(pid: str) -> dict[str, str]:
    profile = db.get_profile(pid)
    if not profile:
        raise HTTPException(404, "Profile không tồn tại")
    return {"url": f"/api/system/file?path={quote(profile['ref_path'])}"}
