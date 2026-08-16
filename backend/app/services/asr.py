"""Speech-to-text with faster-whisper (local). Produces cues → SRT/VTT/TXT/LRC/JSON."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from ..config import MODELS_DIR, settings
from ..jobs import JobContext
from . import audio, ffmpeg, srt as srtlib
from .srt import Cue, Segment, Word
from .text import safe_filename

log = logging.getLogger(__name__)

WHISPER_DIR = MODELS_DIR / "whisper"
WHISPER_DIR.mkdir(parents=True, exist_ok=True)

MODELS: list[dict[str, Any]] = [
    {"name": "tiny", "size_mb": 75, "desc": "Rất nhanh, độ chính xác thấp"},
    {"name": "base", "size_mb": 145, "desc": "Nhanh, dùng thử"},
    {"name": "small", "size_mb": 480, "desc": "Cân bằng (khuyên dùng CPU)"},
    {"name": "medium", "size_mb": 1500, "desc": "Chính xác hơn, chậm trên CPU"},
    {"name": "large-v3-turbo", "size_mb": 1600, "desc": "Chính xác cao, nhanh (khuyên dùng GPU)"},
    {"name": "large-v3", "size_mb": 3100, "desc": "Chính xác nhất, cần GPU ≥ 6GB hoặc rất chậm"},
]

_MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}

_lock = threading.Lock()
_loaded: dict[tuple[str, str, str], Any] = {}


def _model_dir(name: str) -> Path:
    return WHISPER_DIR / name


def is_downloaded(name: str) -> bool:
    d = _model_dir(name)
    return (d / "model.bin").exists() and (d / "config.json").exists()


def list_models() -> list[dict[str, Any]]:
    return [{**m, "downloaded": is_downloaded(m["name"])} for m in MODELS]


def download_model(name: str, progress: Callable[[float, str], None] | None = None) -> Path:
    if name not in _MODEL_REPOS:
        raise ValueError(f"Model không hợp lệ: {name}")
    from huggingface_hub import snapshot_download

    dest = _model_dir(name)
    dest.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(0.05, f"Đang tải model {name} từ Hugging Face…")
    total = next(m["size_mb"] for m in MODELS if m["name"] == name) * (1 << 20)
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
            if progress:
                progress(min(0.95, 0.05 + 0.9 * size / max(total, 1)),
                         f"Đang tải {name}: {size // (1 << 20)}MB / ~{total // (1 << 20)}MB")
            stop.wait(1.0)

    t = threading.Thread(target=poll, daemon=True)
    t.start()
    try:
        snapshot_download(_MODEL_REPOS[name], local_dir=str(dest),
                          allow_patterns=["*.bin", "*.json", "*.txt", "*.model"])
    finally:
        stop.set()
        t.join(timeout=2)
    if progress:
        progress(1.0, "Model sẵn sàng")
    return dest


# ---- device handling ------------------------------------------------------------
def _add_nvidia_libs_to_path() -> None:
    """If nvidia-cublas/cudnn pip wheels are installed, expose their DLLs to ctranslate2."""
    try:
        import nvidia  # type: ignore

        for p in getattr(nvidia, "__path__", []):
            for sub in ("cublas", "cudnn"):
                d = Path(p) / sub / "bin"
                if d.exists():
                    os.environ["PATH"] = f"{d}{os.pathsep}{os.environ.get('PATH', '')}"
                    if hasattr(os, "add_dll_directory"):
                        os.add_dll_directory(str(d))
    except Exception:
        pass


def cuda_available() -> bool:
    try:
        import ctranslate2

        _add_nvidia_libs_to_path()
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def resolve_device(pref: str) -> tuple[str, str]:
    """Return (device, compute_type)."""
    pref = (pref or "auto").lower()
    if pref in ("auto", "cuda") and cuda_available():
        return "cuda", "float16"
    return "cpu", "int8"


def gpu_support_installed() -> bool:
    try:
        import nvidia.cublas  # type: ignore # noqa: F401
        import nvidia.cudnn  # type: ignore # noqa: F401

        return True
    except Exception:
        return False


def install_gpu_support(progress: Callable[[float, str], None] | None = None) -> None:
    """pip install NVIDIA runtime wheels needed by ctranslate2 CUDA (~1GB)."""
    if progress:
        progress(0.1, "Đang cài nvidia-cublas-cu12, nvidia-cudnn-cu12 (~1GB)…")
    subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], capture_output=True)
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--break-system-packages", "nvidia-cublas-cu12", "nvidia-cudnn-cu12"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Cài đặt thất bại: {proc.stderr[-1500:]}")
    if progress:
        progress(1.0, "Đã cài. Khởi động lại ứng dụng để dùng GPU.")


def get_model(name: str, device_pref: str):
    from faster_whisper import WhisperModel

    if not is_downloaded(name):
        raise RuntimeError(f"Model {name} chưa tải. Bấm tải model trước.")
    device, ctype = resolve_device(device_pref)
    key = (name, device, ctype)
    with _lock:
        if key not in _loaded:
            log.info("loading whisper %s on %s/%s", name, device, ctype)
            _loaded.clear()  # keep memory bounded: one model at a time
            _loaded[key] = WhisperModel(str(_model_dir(name)), device=device, compute_type=ctype,
                                        cpu_threads=max(2, (os.cpu_count() or 4) - 1))
        return _loaded[key], device


# ---- vocal separation (optional, demucs) ---------------------------------------------
def demucs_available() -> bool:
    try:
        import demucs  # type: ignore # noqa: F401

        return True
    except Exception:
        return False


def separate_vocals(wav: Path, work: Path, progress: Callable[[float, str], None] | None = None) -> Path:
    if not demucs_available():
        raise RuntimeError("Chưa cài demucs (pip install demucs). Bỏ chọn 'Tách giọng hát' hoặc cài thêm.")
    if progress:
        progress(0.15, "Đang tách giọng hát khỏi nhạc nền (demucs)…")
    out_root = work / "demucs"
    cmd = [sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "-o", str(out_root), str(wav)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"demucs lỗi: {proc.stderr[-1500:]}")
    vocals = next(out_root.rglob("vocals.wav"), None)
    if not vocals:
        raise RuntimeError("demucs không tạo được vocals.wav")
    mono = work / "vocals16k.wav"
    audio.to_wav_mono(vocals, mono, 16000)
    return mono


# ---- transcription --------------------------------------------------------------------
def transcribe(ctx: JobContext, media: Path, model: str = "small", language: str | None = None,
               device: str = "auto", word_timestamps: bool = True, separate: bool = False,
               formats: list[str] | None = None, output_dir: str | None = None,
               initial_prompt: str | None = None) -> dict[str, Any]:
    if not ffmpeg.is_available():
        raise RuntimeError("FFmpeg chưa được cài. Vào Cài đặt → Tải FFmpeg.")
    formats = formats or ["srt"]
    base = Path(output_dir) if output_dir else settings.output_dir
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = base / f"transcript_{safe_filename(media.stem)}_{stamp}"
    work = out_dir / ".work"
    work.mkdir(parents=True, exist_ok=True)

    ctx.progress(0.03, "Đang giải mã audio…")
    wav = audio.to_wav_mono(media, work / "audio16k.wav", 16000)
    duration = ffmpeg.probe_duration(wav) or 0.0
    if separate:
        wav = separate_vocals(wav, work, ctx.progress)

    ctx.progress(0.2, f"Đang nạp model {model}…")
    whisper, dev = get_model(model, device)
    ctx.progress(0.25, f"Đang nhận dạng ({dev})…")

    seg_iter, info = whisper.transcribe(
        str(wav),
        language=language or None,
        task="transcribe",
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
        word_timestamps=word_timestamps,
        initial_prompt=initial_prompt or None,
        condition_on_previous_text=False,
    )
    segments: list[Segment] = []
    for s in seg_iter:
        ctx.check_cancelled()
        words = [Word(w.start, w.end, w.word.strip()) for w in (s.words or []) if w.word.strip()]
        segments.append(Segment(start=s.start, end=s.end, text=s.text.strip(), words=words))
        if duration:
            ctx.progress(0.25 + 0.7 * min(1.0, s.end / duration),
                         f"{srtlib.fmt_srt_time(s.end)[:8]} / {srtlib.fmt_srt_time(duration)[:8]}")

    if word_timestamps and any(seg.words for seg in segments):
        all_words = [w for seg in segments for w in seg.words]
        cues = srtlib.words_to_cues(all_words, max_chars=80, max_duration=6.0)
    else:
        cues = [Cue(seg.start, seg.end, seg.text) for seg in segments if seg.text]
    cues = srtlib.renumber(cues)

    ctx.progress(0.97, "Đang ghi file…")
    stem = safe_filename(media.stem)
    outputs = write_outputs(cues, out_dir, stem, formats, title=media.stem)
    (out_dir / f"{stem}.json").write_text(
        json.dumps({"language": info.language, "duration": duration, "cues": [c.to_dict() for c in cues]},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    return {
        "out_dir": str(out_dir),
        "outputs": outputs,
        "cues": [c.to_dict() for c in cues],
        "language": info.language,
        "language_probability": round(float(info.language_probability or 0), 3),
        "duration": round(duration, 2),
        "device": dev,
        "model": model,
        "source": str(media),
    }


def write_outputs(cues: list[Cue], out_dir: Path, stem: str, formats: list[str], title: str = "") -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    writers = {
        "srt": lambda: srtlib.to_srt(cues),
        "vtt": lambda: srtlib.to_vtt(cues),
        "txt": lambda: srtlib.to_txt(cues),
        "lrc": lambda: srtlib.to_lrc(cues, title),
    }
    for fmt in formats:
        if fmt not in writers:
            continue
        p = out_dir / f"{stem}.{fmt}"
        p.write_text(writers[fmt](), encoding="utf-8")
        outputs.append({"name": p.name, "path": str(p), "kind": fmt})
    return outputs
