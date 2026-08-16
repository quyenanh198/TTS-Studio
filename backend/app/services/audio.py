"""FFmpeg-based audio operations used across TTS / ASR / clone pipelines."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

from . import ffmpeg


def _q(p: str | Path) -> str:
    # concat demuxer requires escaping of single quotes
    return str(p).replace("\\", "/").replace("'", r"'\''")


def concat(inputs: Sequence[Path], out: Path, gap_ms: int = 0) -> Path:
    """Concat inputs (re-encode to target codec). Optional silence gap between parts."""
    if not inputs:
        raise ValueError("no inputs")
    out.parent.mkdir(parents=True, exist_ok=True)
    if len(inputs) == 1 and gap_ms == 0:
        encode(inputs[0], out)
        return out
    lst = out.with_suffix(".txt")
    lines = []
    silence = None
    if gap_ms > 0:
        silence = out.parent / f"_gap_{gap_ms}.wav"
        if not silence.exists():
            make_silence(silence, gap_ms / 1000.0)
    for i, p in enumerate(inputs):
        lines.append(f"file '{_q(p)}'")
        if silence is not None and i < len(inputs) - 1:
            lines.append(f"file '{_q(silence)}'")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ffmpeg.run(["-f", "concat", "-safe", "0", "-i", str(lst), *_codec_args(out), str(out)])
    lst.unlink(missing_ok=True)
    return out


def _codec_args(out: Path, bitrate: str = "128k") -> list[str]:
    ext = out.suffix.lower()
    if ext == ".mp3":
        return ["-vn", "-c:a", "libmp3lame", "-b:a", bitrate, "-ar", "44100", "-ac", "1"]
    if ext == ".wav":
        return ["-vn", "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1"]
    if ext in (".m4a", ".m4b", ".aac"):
        return ["-vn", "-c:a", "aac", "-b:a", bitrate, "-ar", "44100", "-ac", "1"]
    if ext == ".flac":
        return ["-vn", "-c:a", "flac"]
    return ["-vn"]


def encode(src: Path, out: Path, bitrate: str = "128k") -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(["-i", str(src), *_codec_args(out, bitrate), str(out)])
    return out


def to_wav_mono(src: Path, out: Path, sr: int = 16000) -> Path:
    """Decode any media (audio/video) to mono PCM wav at given sample rate."""
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(["-i", str(src), "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(out)])
    return out


def make_silence(out: Path, seconds: float, sr: int = 24000) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(["-f", "lavfi", "-i", f"anullsrc=r={sr}:cl=mono", "-t", f"{seconds:.3f}",
                "-c:a", "pcm_s16le", str(out)])
    return out


def _atempo_chain(rate: float) -> str:
    """ffmpeg atempo only accepts 0.5–2.0 per stage; chain for larger factors."""
    parts = []
    r = rate
    while r > 2.0:
        parts.append("atempo=2.0")
        r /= 2.0
    while r < 0.5:
        parts.append("atempo=0.5")
        r /= 0.5
    parts.append(f"atempo={r:.4f}")
    return ",".join(parts)


def effects_filter(rate: float = 1.0, volume: float = 1.0, keep_pitch: bool = True,
                   pitch_semitones: float = 0.0, sr: int = 24000) -> str | None:
    """Build an -af filter string. Returns None when nothing to apply."""
    filters: list[str] = []
    if not keep_pitch and abs(rate - 1.0) > 1e-3:
        # change pitch together with speed (tape-style)
        filters.append(f"asetrate={sr}*{rate:.4f},aresample={sr}")
    elif abs(rate - 1.0) > 1e-3:
        filters.append(_atempo_chain(rate))
    if abs(pitch_semitones) > 1e-3:
        factor = 2 ** (pitch_semitones / 12.0)
        filters.append(f"asetrate={sr}*{factor:.5f},aresample={sr},{_atempo_chain(1 / factor)}")
    if abs(volume - 1.0) > 1e-3:
        filters.append(f"volume={volume:.3f}")
    return ",".join(filters) if filters else None


def apply_effects(src: Path, out: Path, **kw) -> Path:
    # asetrate needs the REAL input rate (clone WAVs are 22050, TikTok MP3s vary); the default
    # 24000 would silently shift pitch/tempo. Probe unless caller passed sr explicitly.
    if "sr" not in kw:
        kw["sr"] = ffmpeg.probe_sample_rate(src) or 24000
    af = effects_filter(**kw)
    out.parent.mkdir(parents=True, exist_ok=True)
    args = ["-i", str(src)]
    if af:
        args += ["-af", af]
    args += [*_codec_args(out), str(out)]
    ffmpeg.run(args)
    return out


def fit_to_duration(src: Path, out: Path, target: float, max_speedup: float = 1.35) -> tuple[Path, float]:
    """Make audio last exactly `target` seconds: pad with silence if shorter, speed up (≤max) if longer,
    else hard-trim. Returns (path, applied_tempo)."""
    dur = ffmpeg.probe_duration(src) or 0.0
    out.parent.mkdir(parents=True, exist_ok=True)
    if dur <= 0 or target <= 0:
        encode(src, out)
        return out, 1.0
    if dur <= target + 0.02:
        ffmpeg.run(["-i", str(src), "-af", f"apad=whole_dur={target:.3f}", *_codec_args(out), str(out)])
        return out, 1.0
    tempo = min(dur / target, max_speedup)
    ffmpeg.run(["-i", str(src), "-af", f"{_atempo_chain(tempo)},apad=whole_dur={target:.3f}",
                "-t", f"{target:.3f}", *_codec_args(out), str(out)])
    return out, tempo


def make_m4b(inputs: Sequence[Path], titles: Sequence[str], out: Path, book_title: str,
             durations: Sequence[float] | None = None) -> Path:
    """Build an .m4b audiobook with chapter markers."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if durations is None:
        durations = [ffmpeg.probe_duration(p) for p in inputs]
    lst = out.with_suffix(".txt")
    lst.write_text("\n".join(f"file '{_q(p)}'" for p in inputs) + "\n", encoding="utf-8")
    meta = out.with_suffix(".ffmeta")
    lines = [";FFMETADATA1", f"title={_ffmeta(book_title)}", "genre=Audiobook", ""]
    t = 0.0
    for title, d in zip(titles, durations):
        start_ms = int(math.floor(t * 1000))
        end_ms = int(math.floor((t + d) * 1000))
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start_ms}", f"END={end_ms}",
                  f"title={_ffmeta(title)}", ""]
        t += d
    meta.write_text("\n".join(lines), encoding="utf-8")
    ffmpeg.run(["-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(meta), "-map_metadata", "1",
                "-vn", "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "1", "-f", "mp4", str(out)])
    lst.unlink(missing_ok=True)
    meta.unlink(missing_ok=True)
    return out


def _ffmeta(value: str) -> str:
    """Escape ffmetadata special characters (=, ;, #, backslash) and newlines."""
    out = str(value or "").replace("\\", "\\\\")
    for ch in "=;#":
        out = out.replace(ch, "\\" + ch)
    return out.replace("\n", " ").replace("\r", " ")


def duration(path: Path) -> float:
    return ffmpeg.probe_duration(path)
