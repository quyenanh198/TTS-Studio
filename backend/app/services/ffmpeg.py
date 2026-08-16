"""Locate / download FFmpeg and run it.

Resolution order: bundled (DATA_DIR/bin/ffmpeg), PATH, imageio-ffmpeg (if installed).
Windows: downloads gyan.dev release-essentials build (ffmpeg + ffprobe) on demand.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable, Sequence

import httpx

from ..config import BIN_DIR

log = logging.getLogger(__name__)

FFMPEG_DIR = BIN_DIR / "ffmpeg"
FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

_EXE = ".exe" if sys.platform == "win32" else ""


def _find(name: str) -> str | None:
    local = FFMPEG_DIR / f"{name}{_EXE}"
    if local.exists():
        return str(local)
    found = shutil.which(name)
    if found:
        return found
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg  # type: ignore

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None
    return None


def ffmpeg_path() -> str | None:
    return _find("ffmpeg")


def ffprobe_path() -> str | None:
    return _find("ffprobe")


def is_available() -> bool:
    return ffmpeg_path() is not None


def _no_window_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def run(args: Sequence[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("FFmpeg chưa được cài. Vào Cài đặt để tải FFmpeg.")
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", *args]
    log.debug("ffmpeg %s", " ".join(cmd[1:]))
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_no_window_kwargs(),
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"ffmpeg lỗi ({proc.returncode}): {proc.stderr.strip()[-2000:]}")
    return proc


def probe_duration(path: str | Path) -> float:
    """Return media duration in seconds (0.0 if unknown)."""
    exe = ffprobe_path()
    if exe:
        proc = subprocess.run(
            [exe, "-v", "error", "-show_entries", "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **_no_window_kwargs(),
        )
        try:
            return float(proc.stdout.strip())
        except ValueError:
            pass
    ff = ffmpeg_path()
    if not ff:
        return 0.0
    proc = subprocess.run([ff, "-i", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, **_no_window_kwargs())
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", proc.stderr)
    if not m:
        return 0.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def download(progress: Callable[[float, str], None] | None = None) -> str:
    """Download and unpack FFmpeg into FFMPEG_DIR. Returns ffmpeg exe path."""
    if sys.platform != "win32":
        raise RuntimeError("Tự động tải FFmpeg chỉ hỗ trợ Windows. Hãy cài ffmpeg qua package manager.")
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = FFMPEG_DIR / "ffmpeg.zip"
    with httpx.stream("GET", FFMPEG_ZIP_URL, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        done = 0
        with open(zip_path, "wb") as f:
            for chunk in r.iter_bytes(1 << 16):
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total * 0.9,
                             f"Đang tải FFmpeg {done // (1 << 20)}MB/{total // (1 << 20)}MB")
    if progress:
        progress(0.92, "Đang giải nén FFmpeg")
    with zipfile.ZipFile(zip_path) as z:
        for member in z.namelist():
            base = os.path.basename(member)
            if base in ("ffmpeg.exe", "ffprobe.exe"):
                with z.open(member) as src, open(FFMPEG_DIR / base, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    zip_path.unlink(missing_ok=True)
    if progress:
        progress(1.0, "FFmpeg sẵn sàng")
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("Tải FFmpeg thất bại")
    return exe
