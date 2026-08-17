"""Voice cloning via zero-shot voice conversion (Seed-VC).

Pipeline for any language:  text → Edge TTS (target language, gender-matched base voice)
                            → Seed-VC converts timbre to the reference speaker → output.
VC works on audio, not text, so a single reference clip works for every language Edge supports.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from ..config import CACHE_DIR, MODELS_DIR, PROFILES_DIR, settings
from ..db import db
from . import audio, ffmpeg, procs, providers, voices

log = logging.getLogger(__name__)

REF_MAX_SECONDS = 25  # Seed-VC uses at most ~25s of reference
_lock = threading.Lock()        # guards model (un)loading
_infer_lock = threading.Lock()  # one forward pass at a time: torch modules aren't re-entrant, VRAM is finite
_wrapper: Any = None
_wrapper_device: str | None = None


# ---- availability -------------------------------------------------------------------
def torch_info() -> dict[str, Any]:
    try:
        import torch  # type: ignore

        return {"installed": True, "version": torch.__version__, "cuda": bool(torch.cuda.is_available()),
                "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}
    except Exception:
        return {"installed": False, "version": None, "cuda": False, "device_name": None}


def seedvc_installed() -> bool:
    try:
        import seed_vc  # type: ignore # noqa: F401

        return True
    except Exception:
        return False


def resolve_device(pref: str | None = None) -> str:
    pref = (pref or settings.get("vc_device", "auto") or "auto").lower()
    ti = torch_info()
    if pref == "cpu":
        return "cpu"
    return "cuda" if ti["cuda"] else "cpu"


def status() -> dict[str, Any]:
    ti = torch_info()
    installed = ti["installed"] and seedvc_installed()
    device = resolve_device()
    if not ti["installed"]:
        msg = "Chưa cài PyTorch + Seed-VC. Bấm 'Cài đặt Clone giọng' (tải ~2–3 GB)."
    elif not seedvc_installed():
        msg = "Đã có PyTorch nhưng thiếu seed-vc. Bấm cài đặt."
    elif device == "cuda":
        msg = f"Sẵn sàng · GPU {ti['device_name']}"
    else:
        drv = nvidia_driver_cuda()
        hint = ""
        if drv is not None and drv < 11.8:
            hint = f" · Driver NVIDIA quá cũ (CUDA {drv}) — cập nhật driver ≥ 12.x rồi cài lại để dùng GPU"
        elif drv is not None:
            hint = " · Có GPU NVIDIA nhưng PyTorch đang bản CPU — cài lại để bật CUDA"
        msg = "Sẵn sàng · CPU — RẤT chậm (≈1 phút xử lý cho mỗi giây audio), khuyên dùng GPU NVIDIA ≥ 4 GB" + hint
    return {"installed": installed, "device": device, "engines": ["seedvc"] if installed else [],
            "message": msg, "torch": ti, "models_ready": _models_cached()}


def _models_cached() -> bool:
    return (SEEDVC_MODELS_DIR / "models--Plachta--Seed-VC").exists()


def nvidia_driver_cuda() -> float | None:
    """Max CUDA version supported by the installed NVIDIA driver (from nvidia-smi), or None."""
    try:
        import re

        out = procs.run_hidden(["nvidia-smi"], timeout=5).stdout
        m = re.search(r"CUDA Version:\s*([\d.]+)", out)
        return float(m.group(1)) if m else None
    except Exception:
        return None


def _has_nvidia() -> bool:
    return nvidia_driver_cuda() is not None


def _torch_index() -> str:
    """Pick a torch wheel index matching the driver: cu126 (driver ≥ 12.6), cu118 (≥ 11.8), else CPU."""
    v = nvidia_driver_cuda()
    if v is None:
        return "https://download.pytorch.org/whl/cpu"
    if v >= 12.6:
        return "https://download.pytorch.org/whl/cu126"
    if v >= 11.8:
        return "https://download.pytorch.org/whl/cu118"
    return "https://download.pytorch.org/whl/cpu"


def _pip(args: list[str], progress: Callable[[float, str], None] | None, base: float, span: float,
         label: str, should_cancel: Callable[[], bool] | None) -> None:
    """Run pip with live line-by-line progress (collecting/downloading/installing) and cancel support."""
    seen = {"n": 0}

    def on_line(line: str) -> None:
        seen["n"] += 1
        low = line.strip()
        if any(k in low for k in ("Collecting", "Downloading", "Installing", "Successfully", "Using cached")):
            if progress:
                progress(min(base + span * 0.95, base + span * (0.05 + seen["n"] / 60.0)), f"{label}: {low[:90]}")

    code, tail = procs.run_streaming([sys.executable, "-m", "pip", "install", "--break-system-packages",
                                      "--progress-bar", "off", *args], on_line=on_line, should_cancel=should_cancel)
    if code != 0:
        raise RuntimeError(f"{label} thất bại: {tail[-1500:]}")


def install(progress: Callable[[float, str], None] | None = None,
            should_cancel: Callable[[], bool] | None = None) -> None:
    """pip install torch (CUDA if NVIDIA present) + seed-vc. Long: 2–3 GB. Cancellable."""
    procs.run_hidden([sys.executable, "-m", "ensurepip", "--upgrade"])
    if not torch_info()["installed"]:
        idx = _torch_index()
        if progress:
            progress(0.05, f"Đang cài PyTorch ({'CUDA' if 'cu1' in idx else 'CPU'}) ~2 GB…")
        pkgs = ["torch", "torchaudio", "torchvision"]
        if idx.endswith("cu118"):  # newest torch has no cu118 wheels; 2.7.1 is the last one
            pkgs = ["torch==2.7.1", "torchaudio==2.7.1", "torchvision==0.22.1"]
        _pip([*pkgs, "--index-url", idx], progress, 0.05, 0.55, "Cài PyTorch", should_cancel)
    if progress:
        progress(0.6, "Đang cài seed-vc và phụ thuộc…")
    _pip(["seed-vc==0.4.3"], progress, 0.6, 0.3, "Cài seed-vc", should_cancel)
    if progress:
        progress(0.9, "Đang tải model Seed-VC (lần đầu)…")
    try:
        _get_wrapper(resolve_device())
    except Exception as exc:  # noqa: BLE001
        log.warning("seed-vc warmup failed: %s", exc)
    if progress:
        progress(1.0, "Clone giọng sẵn sàng")


# ---- engine ----------------------------------------------------------------------------
SEEDVC_MODELS_DIR = MODELS_DIR / "seedvc"


def _patch_seedvc_compat() -> None:
    """Two shims for seed-vc 0.4.x:
    1. its hf_utils downloads into ./checkpoints (cwd-relative) → redirect to MODELS_DIR/seedvc;
    2. bundled BigVGAN `_from_pretrained` still requires `proxies`/`resume_download` kwargs that
       huggingface_hub ≥ 1.0 no longer passes → fill them in."""
    try:
        import seed_vc.hf_utils as hfu  # type: ignore
        from huggingface_hub import hf_hub_download

        if not getattr(hfu.load_custom_model_from_hf, "_tts_patched", False):
            SEEDVC_MODELS_DIR.mkdir(parents=True, exist_ok=True)

            def load_custom_model_from_hf(repo_id, model_filename="pytorch_model.bin", config_filename=None):
                model_path = hf_hub_download(repo_id=repo_id, filename=model_filename,
                                             cache_dir=str(SEEDVC_MODELS_DIR))
                if config_filename is None:
                    return model_path
                config_path = hf_hub_download(repo_id=repo_id, filename=config_filename,
                                              cache_dir=str(SEEDVC_MODELS_DIR))
                return model_path, config_path

            load_custom_model_from_hf._tts_patched = True  # type: ignore[attr-defined]
            hfu.load_custom_model_from_hf = load_custom_model_from_hf
            # modules that did `from .hf_utils import load_custom_model_from_hf` at import time
            import sys as _sys

            for name, mod in list(_sys.modules.items()):
                if name.startswith("seed_vc") and getattr(mod, "load_custom_model_from_hf", None) is not None:
                    mod.load_custom_model_from_hf = load_custom_model_from_hf
    except Exception as exc:  # noqa: BLE001
        log.debug("seed-vc hf_utils patch skipped: %s", exc)
    try:
        import inspect

        from seed_vc.modules.bigvgan import bigvgan as bv  # type: ignore

        orig = bv.BigVGAN.__dict__.get("_from_pretrained")
        if orig is None or getattr(orig, "_tts_patched", False):
            return
        fn = orig.__func__ if isinstance(orig, classmethod) else orig
        params = inspect.signature(fn).parameters
        needed = [p for p in ("proxies", "resume_download") if p in params]
        if not needed:
            return

        def patched(cls, *args, **kwargs):
            for p in needed:
                kwargs.setdefault(p, None)
            return fn(cls, *args, **kwargs)

        cm = classmethod(patched)
        cm._tts_patched = True  # type: ignore[attr-defined]
        bv.BigVGAN._from_pretrained = cm
    except Exception as exc:  # noqa: BLE001
        log.debug("seed-vc compat patch skipped: %s", exc)


def _slim_wrapper_class():
    """SeedVCWrapper loads the speech model AND the singing/F0 model (+44k BigVGAN, RMVPE) — ~2.7 GB
    on GPU, too much for 4 GB cards. We only use the speech (non-F0) path, so skip the rest."""
    import torch  # type: ignore
    from seed_vc.hf_utils import load_custom_model_from_hf  # type: ignore
    from seed_vc.modules.bigvgan import bigvgan  # type: ignore
    from seed_vc.modules.campplus.DTDNN import CAMPPlus  # type: ignore
    from seed_vc.seed_vc_wrapper import SeedVCWrapper  # type: ignore

    class SlimSeedVC(SeedVCWrapper):  # type: ignore[misc]
        def _load_f0_model(self):  # noqa: D401
            self.model_f0 = None
            self.to_mel_f0 = None

        def _load_additional_modules(self):
            ckpt = load_custom_model_from_hf("funasr/campplus", "campplus_cn_common.bin", config_filename=None)
            self.campplus_model = CAMPPlus(feat_dim=80, embedding_size=192)
            self.campplus_model.load_state_dict(torch.load(ckpt, map_location="cpu"))
            self.campplus_model.eval().to(self.device)
            self.bigvgan_model = bigvgan.BigVGAN.from_pretrained("nvidia/bigvgan_v2_22khz_80band_256x",
                                                                 use_cuda_kernel=False,
                                                                 cache_dir=str(SEEDVC_MODELS_DIR))
            self.bigvgan_model.remove_weight_norm()
            self.bigvgan_model = self.bigvgan_model.eval().to(self.device)
            self.bigvgan_44k_model = None
            self.rmvpe = None

    return SlimSeedVC


def _verify_cache() -> list[str]:
    """Hugging Face cache uses symlinks snapshots/ → blobs/. A copy made without symlink support (or an
    interrupted download) leaves dangling links / pseudo-symlink files that fail with EINVAL/ENOENT at
    open time. Remove any repo whose snapshot files can't actually be read; HF re-downloads on demand."""
    removed: list[str] = []
    for repo in SEEDVC_MODELS_DIR.glob("models--*"):
        snaps = repo / "snapshots"
        if not snaps.is_dir():
            continue
        broken = False
        for f in snaps.rglob("*"):
            if f.is_dir() and not f.is_symlink():
                continue
            try:
                with open(f, "rb") as fh:
                    fh.read(1)
            except OSError:
                broken = True
                break
        if broken:
            log.warning("seed-vc cache repo %s is corrupt — removing for re-download", repo.name)
            _discard_dir(repo)
            removed.append(repo.name)
    # Old snapshots left behind by an earlier version (symlink layout) — never used, best-effort cleanup.
    for junk in SEEDVC_MODELS_DIR.glob("*.broken-*"):
        _rmtree_relative(junk)
    return removed


def _discard_dir(path: Path) -> None:
    """Get a broken HF repo dir out of the way. Broken symlinks on some Windows setups cannot even be
    deleted through absolute paths (WinError 448 / ENOENT / EINVAL), but renaming the *directory* works,
    so: rename aside first (HF then re-downloads into a fresh dir), then try to delete via relative paths."""
    import time

    aside = path.with_name(f"{path.name}.broken-{int(time.time())}")
    try:
        os.rename(path, aside)
    except OSError as exc:
        log.warning("cannot rename %s: %s", path, exc)
        aside = path
    _rmtree_relative(aside)


def _rmtree_relative(root: Path) -> None:
    """rmtree that unlinks entries by *relative* name from inside their directory (works for symlinks
    that fail through absolute paths). Best-effort; leaves whatever cannot be removed."""
    import shutil

    cwd = os.getcwd()
    try:
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            try:
                os.chdir(dirpath)
                for n in filenames + dirnames:
                    try:
                        if os.path.isdir(n) and not os.path.islink(n):
                            os.rmdir(n)
                        else:
                            os.unlink(n)
                    except OSError:
                        pass
            except OSError:
                pass
        os.chdir(cwd)
        shutil.rmtree(root, ignore_errors=True)
    finally:
        try:
            os.chdir(cwd)
        except OSError:
            pass


def _get_wrapper(device: str):
    global _wrapper, _wrapper_device
    with _lock:
        if _wrapper is None or _wrapper_device != device:
            import torch  # type: ignore

            _verify_cache()
            _patch_seedvc_compat()
            cls = _slim_wrapper_class()
            log.info("loading Seed-VC (slim) on %s", device)
            _wrapper = None
            if device == "cuda":
                torch.cuda.empty_cache()
            _wrapper = cls(device=torch.device(device))
            _wrapper_device = device
        return _wrapper


def _drain(result: Any) -> Any:
    """`convert_voice` is a generator function even when stream_output=False: iterate to the end
    and prefer the generator's return value, else the last yielded full_audio."""
    import inspect

    if not inspect.isgenerator(result):
        return result
    last = None
    while True:
        try:
            last = next(result)
        except StopIteration as stop:
            if stop.value is not None:
                return stop.value
            if isinstance(last, tuple) and len(last) == 2:
                return last[1]
            return last


def convert(src: Path, profile: dict[str, Any], out: Path, diffusion_steps: int | None = None,
            device: str | None = None) -> Path:
    """Convert timbre of `src` (any language speech) to the profile's reference speaker."""
    if not seedvc_installed():
        raise RuntimeError("Chưa cài Seed-VC. Vào trang Clone giọng → Cài đặt.")
    import numpy as np  # type: ignore
    import soundfile as sf  # type: ignore

    dev = device or resolve_device()
    default_steps = 25 if dev == "cuda" else 10  # CPU: ~1 min per step per 5 s of audio → keep low
    steps = diffusion_steps or int(settings.get("vc_steps", 0) or default_steps)
    ref = Path(profile["ref_path"])
    if not ref.exists():
        raise RuntimeError("File giọng mẫu không tồn tại")
    # Seed-VC wants a clean wav source
    src_wav = out.parent / f"{src.stem}_src22k.wav"
    audio.to_wav_mono(src, src_wav, 22050)
    def _run(on_device: str):
        w = _get_wrapper(on_device)
        return _drain(w.convert_voice(str(src_wav), str(ref), diffusion_steps=steps, length_adjust=1.0,
                                      inference_cfg_rate=0.7, f0_condition=False, auto_f0_adjust=True,
                                      pitch_shift=0, stream_output=False))

    global _wrapper, _wrapper_device
    with _infer_lock:  # serialize forward passes (thread-safety + VRAM)
        try:
            wav = _run(dev)
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower() and dev == "cuda":
                log.warning("CUDA OOM, retrying on CPU (slow)")
                import gc

                import torch  # type: ignore

                with _lock:  # drop the CUDA copy before loading a CPU one
                    _wrapper = None
                    _wrapper_device = None
                gc.collect()
                torch.cuda.empty_cache()
                wav = _run("cpu")
            else:
                raise
    if wav is None:
        raise RuntimeError("Seed-VC không trả về audio")
    wav = np.asarray(wav, dtype=np.float32).squeeze()
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), wav, 22050)
    src_wav.unlink(missing_ok=True)
    return out


# ---- profiles ---------------------------------------------------------------------------
def prepare_reference(upload: Path, profile_id: str) -> Path:
    """Normalise a reference clip: mono 22.05k wav, trim silence, cap length."""
    pdir = PROFILES_DIR / profile_id
    pdir.mkdir(parents=True, exist_ok=True)
    out = pdir / "ref.wav"
    af = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.2,"
          "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.2,areverse,"
          "loudnorm=I=-20:TP=-2:LRA=11")
    ffmpeg.run(["-i", str(upload), "-vn", "-ac", "1", "-ar", "22050", "-af", af, "-t", str(REF_MAX_SECONDS),
                "-c:a", "pcm_s16le", str(out)])
    return out


def create_profile(name: str, gender: str, language: str, upload: Path, notes: str = "",
                   base_voice: str | None = None) -> dict[str, Any]:
    pid = uuid.uuid4().hex[:10]
    ref = prepare_reference(upload, pid)
    dur = ffmpeg.probe_duration(ref)
    if dur < 3:
        raise RuntimeError("Giọng mẫu quá ngắn (cần ≥ 3 giây, khuyên dùng 10–25 giây nói rõ, không nhạc nền)")
    profile = {"id": pid, "name": name.strip() or f"Giọng {pid}", "gender": gender if gender in ("female", "male") else "female",
               "language": language or "vi", "ref_path": str(ref), "engine": "seedvc", "base_voice": base_voice,
               "notes": notes}
    db.insert_profile(profile)
    return db.get_profile(pid)  # type: ignore[return-value]


def delete_profile(pid: str) -> None:
    db.delete_profile(pid)
    import shutil

    shutil.rmtree(PROFILES_DIR / pid, ignore_errors=True)


def preview(profile: dict[str, Any], lang: str, progress: Callable[[float, str], None] | None = None) -> Path:
    """Synthesize sample text in `lang` with a gender-matched Edge voice, then convert."""
    pdir = PROFILES_DIR / profile["id"]
    out = pdir / f"preview_{lang}.wav"
    if out.exists():
        return out
    base = profile.get("base_voice")
    if not base or not any(v["id"] == base and v["lang"] == lang for v in voices.edge_voices()):
        base = next((v["id"] for v in voices.edge_voices()
                     if v["lang"] == lang and v["gender"] == profile.get("gender", "female")), None)
        base = base or next((v["id"] for v in voices.edge_voices() if v["lang"] == lang), "en-US-JennyNeural")
    if progress:
        progress(0.1, f"Đang tạo giọng gốc ({base})…")
    raw = CACHE_DIR / f"clone_prev_{profile['id']}_{lang}.mp3"
    providers.synth_edge(voices.preview_text(lang), base, raw)
    if progress:
        progress(0.4, "Đang chuyển đổi sang giọng clone…")
    convert(raw, profile, out)
    raw.unlink(missing_ok=True)
    if progress:
        progress(1.0, "Xong")
    return out
