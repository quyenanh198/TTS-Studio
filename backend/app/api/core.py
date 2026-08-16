"""Core endpoints: system info, settings, jobs, websocket progress."""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import DATA_DIR, settings
from ..jobs import JobContext, jobs
from ..services import ffmpeg, procs

router = APIRouter()
_TIKTOK_MASK = "••••••••"


def _is_within(p: Path, root: Path) -> bool:
    try:
        return p.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


# ---- system -----------------------------------------------------------------
def gpu_info() -> dict[str, Any]:
    info: dict[str, Any] = {"cuda": False, "name": None, "vram_mb": None, "torch": None}
    try:
        import torch  # type: ignore

        info["torch"] = torch.__version__
        if torch.cuda.is_available():
            info["cuda"] = True
            info["name"] = torch.cuda.get_device_name(0)
            info["vram_mb"] = int(torch.cuda.get_device_properties(0).total_memory // (1 << 20))
            return info
    except Exception:
        pass
    # nvidia-smi fallback (torch missing / cpu build)
    try:
        out = procs.run_hidden(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], timeout=5,
        ).stdout.strip().splitlines()
        if out:
            name, mem = [s.strip() for s in out[0].split(",")[:2]]
            info.update({"name": name, "vram_mb": int(float(mem)), "cuda": info["cuda"]})
    except Exception:
        pass
    return info


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


@router.get("/system")
def system_info() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "data_dir": str(DATA_DIR),
        "ffmpeg": ffmpeg.ffmpeg_path(),
        "ffprobe": ffmpeg.ffprobe_path(),
        "gpu": gpu_info(),
        "modules": {
            "faster_whisper": _module_available("faster_whisper"),
            "torch": _module_available("torch"),
            "seed_vc": _module_available("seed_vc"),
        },
    }


@router.post("/system/ffmpeg/install")
def install_ffmpeg() -> dict[str, Any]:
    if ffmpeg.is_available():
        return {"already": True, "path": ffmpeg.ffmpeg_path()}

    def job(ctx: JobContext) -> dict[str, Any]:
        path = ffmpeg.download(progress=ctx.progress, should_cancel=lambda: ctx.cancelled)
        return {"path": path}

    return jobs.submit("ffmpeg_install", {}, job)


class OpenPath(BaseModel):
    path: str


@router.post("/system/open")
def open_path(body: OpenPath) -> dict[str, bool]:
    p = Path(body.path)
    if not p.exists():
        raise HTTPException(404, "Không tìm thấy đường dẫn")
    if sys.platform == "win32":
        if p.is_file():
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            os.startfile(str(p))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])
    return {"ok": True}


@router.get("/system/file")
def serve_file(path: str):
    """Serve a local file (audio preview / download) — restricted to data/output dirs."""
    p = Path(path).resolve()
    allowed = [DATA_DIR.resolve(), settings.output_dir.resolve()]
    if not any(_is_within(p, a) for a in allowed):
        raise HTTPException(403, "Không được phép")
    if not p.is_file():
        raise HTTPException(404, "Không tìm thấy file")
    return FileResponse(str(p), filename=p.name)


# ---- settings -----------------------------------------------------------------
def _public_settings() -> dict[str, Any]:
    s = settings.all()
    s["tiktok_session_id"] = _TIKTOK_MASK if s.get("tiktok_session_id") else ""
    return s


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    return _public_settings()


@router.put("/settings")
def put_settings(body: dict[str, Any]) -> dict[str, Any]:
    body = dict(body)
    if body.get("tiktok_session_id") == _TIKTOK_MASK:
        body.pop("tiktok_session_id")  # unchanged masked value → keep stored secret
    if "output_dir" in body:
        raw = str(body["output_dir"] or "").strip()
        p = Path(raw)
        if not raw or not p.is_absolute():
            raise HTTPException(422, "Thư mục xuất phải là đường dẫn tuyệt đối")
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(422, f"Không tạo được thư mục: {exc}") from exc
        body["output_dir"] = str(p.resolve())
    try:
        settings.update(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _public_settings()


# ---- jobs -----------------------------------------------------------------------
@router.get("/jobs")
def list_jobs(limit: int = 100, kind: str | None = None) -> list[dict[str, Any]]:
    return jobs.list(limit=limit, kind=kind)


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job không tồn tại")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, bool]:
    return {"ok": jobs.cancel(job_id)}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str) -> dict[str, bool]:
    jobs.delete(job_id)
    return {"ok": True}


@router.websocket("/ws/jobs")
async def ws_jobs(ws: WebSocket) -> None:
    await ws.accept()
    q = jobs.subscribe()
    try:
        while True:
            try:
                job = await asyncio.wait_for(q.get(), timeout=20)
                await ws.send_json({"type": "job", "job": job})
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        jobs.unsubscribe(q)
