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
from ..services import clone, f5, ffmpeg
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


@router.get("/clone/f5/status")
def f5_status() -> dict[str, Any]:
    return f5.status()


@router.post("/clone/f5/install")
def f5_install() -> dict[str, Any]:
    active = [j for j in jobs.list(kind="f5_install", limit=5) if j["status"] in ("queued", "running")]
    if active:
        return active[0]

    def job(ctx: JobContext) -> dict[str, Any]:
        f5.install(ctx.progress, should_cancel=lambda: ctx.cancelled)
        return f5.status()

    return jobs.submit("f5_install", {"title": "Cài đặt F5-TTS Việt (offline)"}, job)


@router.get("/clone/emotions")
def emotions() -> list[dict[str, str]]:
    return [{"id": e, "label": lb} for e, lb in f5.EMOTIONS]


def _with_samples(p: dict[str, Any]) -> dict[str, Any]:
    p = dict(p)
    p["samples"] = f5.list_samples(p["id"]) if p.get("engine") == "f5vi" else []
    return p


@router.get("/clone/profiles")
def list_profiles() -> list[dict[str, Any]]:
    return [_with_samples(p) for p in db.list_profiles()]


@router.post("/clone/profiles")
async def create_profile(
    name: str = Form(...),
    gender: str = Form("female"),
    language: str = Form("vi"),
    notes: str = Form(""),
    base_voice: str | None = Form(None),
    engine: str = Form("seedvc"),
    ref_text: str = Form(""),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if engine not in ("seedvc", "f5vi"):
        raise HTTPException(422, "engine phải là seedvc hoặc f5vi")
    if not ffmpeg.is_available():
        raise HTTPException(409, "FFmpeg chưa được cài (Cài đặt → Tải FFmpeg)")
    ext = Path(file.filename or "ref.wav").suffix.lower() or ".wav"
    dest = UPLOAD_DIR / f"{int(time.time())}_{safe_filename(Path(file.filename or 'ref').stem)}{ext}"
    with open(dest, "wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)
    try:
        # ffmpeg loudnorm etc. is blocking — keep it off the event loop
        prof = await run_in_threadpool(clone.create_profile, name, gender, language, dest, notes, base_voice or None)
        if engine == "f5vi":
            db.update_profile(prof["id"], engine="f5vi")
            try:
                await run_in_threadpool(f5.add_sample, prof["id"], "neutral", dest, ref_text or None)
            except (RuntimeError, ValueError):
                clone.delete_profile(prof["id"])
                raise
            prof = db.get_profile(prof["id"]) or prof
        return _with_samples(prof)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        dest.unlink(missing_ok=True)


@router.post("/clone/profiles/{pid}/samples")
async def add_sample(pid: str, emotion: str = Form(...), text: str = Form(""),
                     file: UploadFile = File(...)) -> dict[str, Any]:
    if not db.get_profile(pid):
        raise HTTPException(404, "Profile không tồn tại")
    ext = Path(file.filename or "s.wav").suffix.lower() or ".wav"
    dest = UPLOAD_DIR / f"{int(time.time())}_{pid}_{safe_filename(emotion)}{ext}"
    with open(dest, "wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)
    try:
        return await run_in_threadpool(f5.add_sample, pid, emotion, dest, text or None)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        dest.unlink(missing_ok=True)


@router.delete("/clone/profiles/{pid}/samples/{emotion}")
def delete_sample(pid: str, emotion: str) -> dict[str, bool]:
    if not db.get_profile(pid):
        raise HTTPException(404, "Profile không tồn tại")
    f5.remove_sample(pid, emotion)
    return {"ok": True}


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
    return _with_samples(db.get_profile(pid))  # type: ignore[arg-type]


@router.delete("/clone/profiles/{pid}")
def delete_profile(pid: str) -> dict[str, bool]:
    clone.delete_profile(pid)
    return {"ok": True}


class PreviewBody(BaseModel):
    lang: str = "vi"
    emotion: str | None = None


_F5_PREVIEW = {
    "neutral": "Xin chào, đây là giọng đọc của tôi. Hôm nay chúng ta cùng bắt đầu một câu chuyện mới nhé.",
    "sad": "Tôi đứng lặng nhìn theo bóng người khuất dần, lòng nặng trĩu một nỗi buồn không tên...",
    "happy": "Tuyệt vời quá! Cuối cùng chúng ta cũng làm được rồi, vui không thể tả!",
    "angry": "Đủ rồi! Tôi không thể chịu đựng thêm một lời dối trá nào nữa!",
    "fear": "Có tiếng bước chân sau lưng... tôi nín thở, tim đập thình thịch trong bóng tối.",
    "calm": "Nhẹ nhàng thôi, hít một hơi thật sâu, mọi chuyện rồi sẽ ổn cả.",
}


@router.post("/clone/profiles/{pid}/preview")
def preview_profile(pid: str, body: PreviewBody) -> dict[str, Any]:
    profile = db.get_profile(pid)
    if not profile:
        raise HTTPException(404, "Profile không tồn tại")
    if profile.get("engine") == "f5vi":
        if not f5.status()["installed"]:
            raise HTTPException(409, "Chưa cài F5-TTS Việt")
        emo = body.emotion or "neutral"
        if emo not in _F5_PREVIEW:
            raise HTTPException(422, "Cảm xúc không hợp lệ")

        def job_f5(ctx: JobContext) -> dict[str, Any]:
            f5.ensure_from_ref(profile)
            by = {s["emotion"]: s for s in f5.list_samples(pid)}
            sample = by.get(emo) or by.get("neutral") or next(iter(by.values()))
            out = Path(profile["ref_path"]).parent / f"preview_f5_{emo}.wav"
            ctx.progress(0.2, f"F5-TTS đang đọc mẫu ({emo})…")
            f5.synth(_F5_PREVIEW[emo], Path(sample["wav"]), sample["text"], out)
            return {"path": str(out), "url": f"/api/system/file?path={quote(str(out))}", "lang": f"emo:{emo}",
                    "profile": pid}

        return jobs.submit("clone_preview", {"title": f"Nghe thử {profile['name']} ({emo})", "profile": pid,
                                              "lang": f"emo:{emo}"}, job_f5)
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
