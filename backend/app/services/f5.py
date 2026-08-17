"""F5-TTS Vietnamese engine (offline, zero-shot voice clone, emotion via reference samples).

Model: hynt/F5-TTS-Vietnamese-ViVoice (F5TTS_Base fine-tuned on ~1000 h Vietnamese, CC-BY-NC-SA-4.0 —
non-commercial). Emotion is not a tag: it comes from the *reference clip*, so a profile keeps a small
set of samples (neutral / sad / happy / angry / fear / calm) and the engine picks one per sentence
from the prosody tags.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import unicodedata
from pathlib import Path
from typing import Any, Callable

from ..config import MODELS_DIR, PROFILES_DIR, settings
from . import ffmpeg

log = logging.getLogger(__name__)

F5_DIR = MODELS_DIR / "f5vi"
REPO = "hynt/F5-TTS-Vietnamese-ViVoice"
CKPT = F5_DIR / "model_last.pt"
VOCAB = F5_DIR / "vocab.txt"
VOCOS_REPO = "charactr/vocos-mel-24khz"
VOCOS_DIR = F5_DIR / "vocos"  # plain files (no HF symlink cache — unreliable on some Windows setups)
LICENSE_NOTE = "Model F5-TTS Việt (hynt/F5-TTS-Vietnamese-ViVoice) — giấy phép CC-BY-NC-SA-4.0: chỉ dùng phi thương mại."

EMOTIONS: list[tuple[str, str]] = [
    ("neutral", "Kể chuyện / trung tính"),
    ("sad", "Buồn"),
    ("happy", "Vui"),
    ("angry", "Giận / gay gắt"),
    ("fear", "Sợ / hồi hộp"),
    ("calm", "Nhẹ nhàng / thì thầm"),
]
_TAG_TO_EMOTION = {"sad": "sad", "trailing": "sad", "joy": "happy", "exclaim": "happy", "anger": "angry",
                   "fear": "fear", "calm": "calm"}
MAX_GEN_CHARS = 220  # ≈ 12–15 s of Vietnamese; ref + gen must stay well under the 30 s training window

_lock = threading.Lock()
_infer_lock = threading.Lock()
_model: Any = None
_model_device: str | None = None


# ---- availability / install -----------------------------------------------------------------
def installed() -> bool:
    try:
        import f5_tts  # type: ignore # noqa: F401

        return True
    except Exception:
        return False


def _vocos_ready() -> bool:
    cfg, bin_ = VOCOS_DIR / "config.yaml", VOCOS_DIR / "pytorch_model.bin"
    return cfg.is_file() and bin_.is_file() and bin_.stat().st_size > 10_000_000


def models_ready() -> bool:
    return CKPT.exists() and CKPT.stat().st_size > 100_000_000 and VOCAB.exists() and _vocos_ready()


def status() -> dict[str, Any]:
    from . import clone

    ti = clone.torch_info()
    ok = ti["installed"] and installed()
    return {"installed": ok, "models_ready": models_ready(), "device": clone.resolve_device(),
            "license": LICENSE_NOTE, "torch": ti,
            "message": ("Sẵn sàng" if ok and models_ready() else
                        "Chưa tải model" if ok else "Chưa cài f5-tts (cần PyTorch)")}


def download(progress: Callable[[float, str], None] | None = None) -> None:
    from huggingface_hub import hf_hub_download

    F5_DIR.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(0.05, "Đang tải F5-TTS Việt (~1.3 GB)…")
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            size = sum(f.stat().st_size for f in F5_DIR.rglob("*") if f.is_file())
            if progress:
                progress(min(0.95, 0.05 + 0.9 * size / (1.35 * (1 << 30))), f"Đang tải model: {size // (1 << 20)} MB")
            stop.wait(1.0)

    threading.Thread(target=poll, daemon=True).start()
    try:
        # local_dir → real files (no blobs/snapshots symlink layout)
        p = hf_hub_download(REPO, "model_last.pt", local_dir=str(F5_DIR))
        v = hf_hub_download(REPO, "config.json", local_dir=str(F5_DIR))  # this file IS the vocab
        if Path(p).resolve() != CKPT.resolve():
            shutil.copy(p, CKPT)
        shutil.copy(v, VOCAB)
        VOCOS_DIR.mkdir(parents=True, exist_ok=True)
        for fn in ("config.yaml", "pytorch_model.bin"):
            hf_hub_download(VOCOS_REPO, fn, local_dir=str(VOCOS_DIR))
    finally:
        stop.set()
    if progress:
        progress(1.0, "Model F5-TTS Việt sẵn sàng")


def install(progress: Callable[[float, str], None] | None = None,
            should_cancel: Callable[[], bool] | None = None) -> None:
    from . import clone

    if not clone.torch_info()["installed"]:
        clone.install(progress=(lambda v, m="": progress(v * 0.6, m)) if progress else None,
                      should_cancel=should_cancel)
    if not installed():
        if progress:
            progress(0.62, "Đang cài f5-tts…")
        clone._pip(["f5-tts==1.1.22"], progress, 0.62, 0.18, "Cài f5-tts", should_cancel)  # noqa: SLF001
    if not models_ready():
        download((lambda v, m="": progress(0.8 + 0.16 * v, m)) if progress else None)
    # Whisper for auto-transcribing reference/emotion samples (ref_text is mandatory for F5).
    if _asr_model_name() is None:
        from . import asr

        if progress:
            progress(0.96, f"Đang tải Whisper {ASR_FALLBACK_MODEL} để nhận dạng lời mẫu…")
        try:
            asr.download_model(ASR_FALLBACK_MODEL, (lambda v, m="": progress(0.96 + 0.04 * v, m)) if progress else None)
        except Exception as exc:  # noqa: BLE001 — optional: user can still type the ref text
            log.warning("whisper %s download failed: %s", ASR_FALLBACK_MODEL, exc)
    if progress:
        progress(1.0, "F5-TTS Việt sẵn sàng")


# ---- inference -----------------------------------------------------------------------------
_dtype_pinned = False


def _pin_dtype(device: str) -> None:
    """f5_tts loads the DiT in float16 on any GPU with compute capability ≥ 7. On Turing (GTX 16xx /
    RTX 20xx, sm 7.5) that yields NaN → full-scale noise, and is ~4× slower than fp32 there.
    Keep fp16 for Ampere+ only."""
    global _dtype_pinned
    if _dtype_pinned:
        return
    _dtype_pinned = True
    try:
        import torch
        from f5_tts.infer import utils_infer as U  # type: ignore

        if "cuda" in device and torch.cuda.get_device_properties(device).major >= 8:
            return
        orig = U.load_checkpoint

        def load_checkpoint(model, ckpt_path, dev, dtype=None, use_ema=True):  # noqa: ANN001
            return orig(model, ckpt_path, dev, dtype=torch.float32, use_ema=use_ema)

        U.load_checkpoint = load_checkpoint
        log.info("F5-TTS pinned to float32 on %s", device)
    except Exception as exc:  # noqa: BLE001
        log.warning("F5 dtype pin failed: %s", exc)


def _get(device: str):
    global _model, _model_device
    with _lock:
        if _model is None or _model_device != device:
            if not models_ready():
                raise RuntimeError("Model F5-TTS Việt chưa tải (trang Clone giọng → Cài đặt F5-TTS).")
            from f5_tts.api import F5TTS  # type: ignore

            _pin_dtype(device)
            log.info("loading F5-TTS vi on %s", device)
            _model = F5TTS(model="F5TTS_Base", ckpt_file=str(CKPT), vocab_file=str(VOCAB), device=device,
                           vocoder_local_path=str(VOCOS_DIR), hf_cache_dir=str(MODELS_DIR / "hf"))
            _model_device = device
        return _model


def normalize_vi(text: str) -> str:
    """Model card: lowercase, keep punctuation."""
    t = unicodedata.normalize("NFC", text or "").lower()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def synth(text: str, ref_wav: Path, ref_text: str, out: Path, speed: float = 1.0, nfe: int = 32,
          device: str | None = None) -> Path:
    from . import clone

    dev = device or clone.resolve_device()
    out.parent.mkdir(parents=True, exist_ok=True)
    with _infer_lock:
        m = _get(dev)
        m.infer(ref_file=str(ref_wav), ref_text=normalize_vi(ref_text), gen_text=normalize_vi(text),
                speed=max(0.5, min(2.0, speed)), nfe_step=nfe, remove_silence=False, file_wave=str(out),
                show_info=lambda *a, **k: None, progress=None, seed=None)
    return out


# ---- emotion samples per profile -------------------------------------------------------------
def _samples_file(pid: str) -> Path:
    return PROFILES_DIR / pid / "samples.json"


def list_samples(pid: str) -> list[dict[str, Any]]:
    f = _samples_file(pid)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_samples(pid: str, items: list[dict[str, Any]]) -> None:
    _samples_file(pid).parent.mkdir(parents=True, exist_ok=True)
    _samples_file(pid).write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


ASR_FALLBACK_MODEL = "small"  # ~460 MB; decent Vietnamese for short, clean reference clips


def _asr_model_name() -> str | None:
    """Preferred downloaded Whisper model: the user's setting if present, else the largest downloaded."""
    from . import asr

    pref = settings.get("asr_model", ASR_FALLBACK_MODEL)
    if asr.is_downloaded(pref):
        return pref
    return next((m["name"] for m in reversed(asr.MODELS) if asr.is_downloaded(m["name"])), None)


def transcribe_ref(wav: Path) -> str:
    """Reference text via faster-whisper. Downloads `small` on first use if no model exists.
    Empty string if transcription is impossible (caller asks the user to type the text)."""
    try:
        from . import asr

        name = _asr_model_name()
        if not name:
            log.info("no whisper model — downloading %s for ref transcription", ASR_FALLBACK_MODEL)
            asr.download_model(ASR_FALLBACK_MODEL)
            name = ASR_FALLBACK_MODEL
        model, _dev = asr.get_model(name, settings.get("asr_device", "auto"))
        segs, _info = model.transcribe(str(wav), language="vi", beam_size=5, vad_filter=True)
        return " ".join(s.text.strip() for s in segs).strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("ref transcription failed: %s", exc)
        return ""


def add_sample(pid: str, emotion: str, upload: Path, text: str | None = None) -> dict[str, Any]:
    if emotion not in {e for e, _ in EMOTIONS}:
        raise ValueError("Cảm xúc không hợp lệ")
    sdir = PROFILES_DIR / pid / "samples"
    sdir.mkdir(parents=True, exist_ok=True)
    wav = sdir / f"{emotion}.wav"
    # mono 24 kHz, trim silence, normalise, cap 12 s (ref should stay short so ref+gen < 30 s)
    af = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.2,"
          "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.2,areverse,"
          "loudnorm=I=-20:TP=-2:LRA=11")
    ffmpeg.run(["-i", str(upload), "-vn", "-ac", "1", "-ar", "24000", "-af", af, "-t", "12", "-c:a", "pcm_s16le", str(wav)])
    dur = ffmpeg.probe_duration(wav)
    if dur < 2:
        raise RuntimeError("Mẫu quá ngắn (cần 3–12 giây)")
    ref_text = (text or "").strip() or transcribe_ref(wav)
    if not ref_text:
        raise RuntimeError("Không nhận dạng được lời của mẫu — hãy nhập chính xác lời thoại trong mẫu vào ô "
                           "'Lời thoại' (khuyến nghị), hoặc kiểm tra mạng để app tải model Whisper.")
    items = [s for s in list_samples(pid) if s["emotion"] != emotion]
    item = {"emotion": emotion, "wav": str(wav), "text": ref_text, "duration": round(dur, 2)}
    items.append(item)
    _save_samples(pid, items)
    return item


def remove_sample(pid: str, emotion: str) -> None:
    items = list_samples(pid)
    keep = [s for s in items if s["emotion"] != emotion]
    for s in items:
        if s["emotion"] == emotion:
            Path(s["wav"]).unlink(missing_ok=True)
    _save_samples(pid, keep)


def pick_sample(pid: str, tags: list[str] | None) -> dict[str, Any]:
    """Choose the sample whose emotion best matches the prosody tags; fall back to neutral / any."""
    items = list_samples(pid)
    if not items:
        raise RuntimeError("Profile chưa có mẫu giọng (cần ít nhất mẫu 'Kể chuyện').")
    by = {s["emotion"]: s for s in items}
    for t in tags or []:
        emo = _TAG_TO_EMOTION.get(t)
        if emo and emo in by:
            return by[emo]
    return by.get("neutral") or items[0]


def ensure_from_ref(profile: dict[str, Any]) -> None:
    """A Seed-VC profile switched to F5 uses its ref.wav as the neutral sample."""
    pid = profile["id"]
    if list_samples(pid):
        return
    ref = Path(profile["ref_path"])
    if ref.exists():
        add_sample(pid, "neutral", ref, None)
