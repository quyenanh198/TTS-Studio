"""Optional-component installer, run by Setup at the end of installation (console window visible so
the user can follow pip/ffmpeg progress). Reuses the app's own installers, so everything is exactly
what Settings/Clone pages would do in-app.

Usage: python postinstall.py [--ffmpeg] [--clone] [--whisper-gpu]
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("PYTHONUTF8", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass


def say(msg: str) -> None:
    print(msg, flush=True)


def progress(value: float, msg: str = "") -> None:
    bar = "#" * int(value * 30)
    say(f"  [{bar:<30}] {int(value * 100):3d}%  {msg}")


def main() -> int:
    args = set(sys.argv[1:])
    do_ffmpeg = "--ffmpeg" in args
    do_clone = "--clone" in args
    do_whisper = "--whisper-gpu" in args
    do_f5 = "--f5" in args
    if not (do_ffmpeg or do_clone or do_whisper or do_f5):
        return 0

    say("=" * 70)
    say(" TTS Studio — cài đặt thành phần tuỳ chọn (cần internet)")
    say("=" * 70)
    failures: list[str] = []

    from app.services import clone  # noqa: E402  (imports app config → creates data dir)

    drv = clone.nvidia_driver_cuda()
    if drv is None:
        say(" GPU NVIDIA: không phát hiện → PyTorch bản CPU (clone giọng sẽ rất chậm).")
    else:
        idx = clone._torch_index()  # noqa: SLF001
        flavour = "CUDA 12.6" if idx.endswith("cu126") else "CUDA 11.8" if idx.endswith("cu118") else "CPU (driver quá cũ)"
        say(f" GPU NVIDIA: driver hỗ trợ CUDA {drv} → PyTorch {flavour}.")

    if do_ffmpeg:
        say("\n[1] FFmpeg (~90 MB)")
        try:
            from app.services import ffmpeg

            if ffmpeg.is_available():
                say("  đã có sẵn: " + str(ffmpeg.ffmpeg_path()))
            else:
                ffmpeg.download(progress=progress)
                say("  OK")
        except Exception:  # noqa: BLE001
            failures.append("FFmpeg")
            say(traceback.format_exc()[-1500:])

    if do_clone:
        say("\n[2] Clone giọng — PyTorch + Seed-VC (2–3 GB, có thể mất 10–30 phút)")
        try:
            clone.install(progress=progress)
            st = clone.status()
            say("  OK — " + st["message"])
        except Exception:  # noqa: BLE001
            failures.append("PyTorch/Seed-VC")
            say(traceback.format_exc()[-1500:])

    if do_f5:
        say("\n[2b] F5-TTS Việt — giọng Việt có cảm xúc, offline (f5-tts + model ~1.5 GB; kèm PyTorch nếu chưa có)")
        try:
            from app.services import f5

            f5.install(progress=progress)
            say("  OK — " + f5.status()["message"])
        except Exception:  # noqa: BLE001
            failures.append("F5-TTS Việt")
            say(traceback.format_exc()[-1500:])

    if do_whisper:
        say("\n[3] Tăng tốc GPU cho Whisper — cuBLAS/cuDNN (~1 GB)")
        try:
            from app.services import asr

            asr.install_gpu_support(progress=progress)
            say("  OK")
        except Exception:  # noqa: BLE001
            failures.append("Whisper GPU libs")
            say(traceback.format_exc()[-1500:])

    say("")
    if failures:
        say(" Một số thành phần chưa cài được: " + ", ".join(failures))
        say(" Bạn có thể cài lại bất cứ lúc nào trong app (Cài đặt / Clone giọng / Transcript).")
        say(" Cửa sổ này sẽ tự đóng sau 20 giây.")
        time.sleep(20)
        return 1
    say(" Hoàn tất. Cửa sổ này sẽ tự đóng sau 5 giây.")
    time.sleep(5)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
