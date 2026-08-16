"""TTS job orchestration: chapters → chunks → provider → concat → effects → export modes."""

from __future__ import annotations

import logging
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import settings
from ..jobs import JobContext
from . import audio, ffmpeg, providers, srt as srtlib, text as textlib, voices
from .srt import Cue, Word

log = logging.getLogger(__name__)


@dataclass
class ChapterIn:
    title: str
    text: str
    cues: list[Cue] | None = None  # present when chapter came from an SRT file


@dataclass
class TtsRequest:
    title: str
    chapters: list[ChapterIn]
    voice: str = "vi-VN-HoaiMyNeural"
    rate: float = 1.0
    volume: float = 1.0
    keep_pitch: bool = True
    pitch: float = 0.0  # semitones
    format: str = "mp3"
    export_mode: str = "per_chapter"  # per_chapter | merged | range | per_cue
    range_start: int | None = None
    range_end: int | None = None
    merge_every: int | None = None
    make_srt: bool = True
    make_zip: bool = False
    make_m4b: bool = False
    clone_profile: str | None = None
    output_dir: str | None = None
    gap_ms: int = 700  # silence between chapters when merging

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TtsRequest":
        chapters = []
        for c in d.get("chapters", []):
            cues = None
            if c.get("cues"):
                cues = [Cue(start=float(x["start"]), end=float(x["end"]), text=str(x["text"]), index=i + 1)
                        for i, x in enumerate(c["cues"])]
            chapters.append(ChapterIn(title=c.get("title") or "Chương", text=c.get("text") or "", cues=cues))
        known = {f for f in cls.__dataclass_fields__ if f != "chapters"}
        kw = {k: v for k, v in d.items() if k in known and v is not None}
        return cls(chapters=chapters, **kw)


@dataclass
class ChapterOut:
    title: str
    wav: Path
    cues: list[Cue]
    duration: float
    index: int = 0


@dataclass
class Output:
    name: str
    path: Path
    duration: float
    srt: Path | None = None
    kind: str = "audio"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "path": str(self.path), "duration": round(self.duration, 2),
                "srt": str(self.srt) if self.srt else None, "kind": self.kind}


# --------------------------------------------------------------------------------------
class Progress:
    def __init__(self, ctx: JobContext, total_units: int):
        self.ctx = ctx
        self.total = max(1, total_units)
        self.done = 0

    def tick(self, units: int = 1, msg: str = "") -> None:
        self.done += units
        self.ctx.progress(min(0.97, self.done / self.total * 0.95), msg)


def _provider_for(voice: str) -> str:
    return voices.provider_of(voice)


def _synth_chunk(provider: str, text: str, voice: str, out: Path, req: TtsRequest,
                 neutral: bool = False) -> providers.SynthResult:
    """`neutral=True` synthesises at 1.0x / 0dB / 0st — used when effects are applied later by
    ffmpeg (clone pipeline) so they are never applied twice."""
    if provider == "tiktok":
        return providers.synth_tiktok(text, voice, out, settings.get("tiktok_session_id", ""))
    if neutral:
        return providers.synth_edge(text, voice, out)
    # edge: native rate/volume/pitch (better quality than post-processing)
    return providers.synth_edge(text, voice, out, rate=req.rate, volume=req.volume,
                                pitch_semitones=req.pitch if req.keep_pitch else 0.0)


def _base_voice_for_clone(req: TtsRequest, profile: dict[str, Any], lang_hint: str | None) -> str:
    """Pick an Edge base voice matching profile gender + requested language."""
    if req.voice and not req.voice.startswith("clone:"):
        return req.voice
    if profile.get("base_voice"):
        return profile["base_voice"]
    lang = lang_hint or profile.get("language") or "vi"
    gender = profile.get("gender", "female")
    for v in voices.edge_voices():
        if v["lang"] == lang and v["gender"] == gender:
            return v["id"]
    return "vi-VN-HoaiMyNeural"


def synth_chapter(ctx: JobContext, req: TtsRequest, ch: ChapterIn, work: Path, idx: int,
                  prog: Progress) -> ChapterOut:
    """Synthesise one chapter to a WAV in `work`, returning cues relative to chapter start."""
    provider = _provider_for(req.voice)
    clone_profile = None
    voice = req.voice
    if req.clone_profile or provider == "clone":
        from ..db import db

        pid = req.clone_profile or req.voice.split(":", 1)[1]
        clone_profile = db.get_profile(pid)
        if not clone_profile:
            raise RuntimeError("Voice profile không tồn tại")
        voice = _base_voice_for_clone(req, clone_profile, None)
        provider = _provider_for(voice)

    ch_dir = work / f"ch{idx:04d}"
    ch_dir.mkdir(parents=True, exist_ok=True)

    # ---- SRT-timed chapter (per_cue): synth each cue, fit to its slot ---------------
    if ch.cues and req.export_mode == "per_cue":
        parts: list[Path] = []
        t = 0.0
        for i, cue in enumerate(ch.cues):
            ctx.check_cancelled()
            raw = ch_dir / f"cue{i:05d}.mp3"
            _synth_chunk(provider, cue.text, voice, raw, req, neutral=clone_profile is not None)
            if clone_profile:
                raw = _clone_convert(raw, clone_profile, ch_dir / f"cue{i:05d}_vc.wav")
            fitted = ch_dir / f"cue{i:05d}.wav"
            audio.fit_to_duration(raw, fitted, max(0.2, cue.end - cue.start))
            gap = cue.start - t
            if gap > 0.02:
                sil = ch_dir / f"sil{i:05d}.wav"
                audio.make_silence(sil, gap)
                parts.append(sil)
            parts.append(fitted)
            t = cue.end
            prog.tick(max(1, len(cue.text)), f"[{ch.title}] cue {i + 1}/{len(ch.cues)}")
        wav = ch_dir / "chapter.wav"
        audio.concat(parts, wav)
        return ChapterOut(title=ch.title, wav=wav, cues=list(ch.cues), duration=audio.duration(wav), index=idx)

    # ---- plain text chapter ------------------------------------------------------------
    max_chars = textlib.TIKTOK_MAX_CHARS if provider == "tiktok" else textlib.MAX_CHUNK_CHARS
    sentences = textlib.split_sentences(textlib.normalize(ch.text))
    chunks = textlib.chunk_sentences(sentences, max_chars)
    if not chunks:
        raise RuntimeError(f"Chương '{ch.title}' không có nội dung")

    parts = []
    all_words: list[Word] = []
    chunk_cues: list[Cue] = []
    offset = 0.0
    for i, chunk in enumerate(chunks):
        ctx.check_cancelled()
        raw = ch_dir / f"c{i:05d}.mp3"
        res = _synth_chunk(provider, chunk, voice, raw, req, neutral=clone_profile is not None)
        dur = ffmpeg.probe_duration(raw) or res.duration
        if res.words:
            aligned = srtlib.attach_punctuation(chunk, res.words)
            all_words.extend(Word(start=w.start + offset, end=w.end + offset, text=w.text) for w in aligned)
        else:
            chunk_cues.append(Cue(start=offset, end=offset + dur, text=chunk))
        parts.append(raw)
        offset += dur
        prog.tick(len(chunk), f"[{ch.title}] {i + 1}/{len(chunks)}")

    wav_raw = ch_dir / "chapter_raw.wav"
    audio.concat(parts, wav_raw)
    cues = srtlib.words_to_cues(all_words) if all_words else chunk_cues

    wav = wav_raw
    if clone_profile:
        wav = _clone_convert(wav_raw, clone_profile, ch_dir / "chapter_vc.wav")
    # Effects via ffmpeg for TikTok and for the clone pipeline (Edge was synthesised neutral in
    # those cases). Plain Edge already applied rate/volume/pitch natively — do NOT apply twice.
    if provider != "edge" or clone_profile:
        eff = ch_dir / "chapter_fx.wav"
        audio.apply_effects(wav, eff, rate=req.rate, volume=req.volume, keep_pitch=req.keep_pitch,
                            pitch_semitones=req.pitch)
        if abs(req.rate - 1.0) > 1e-3:
            cues = srtlib.scale(cues, 1.0 / req.rate)
        wav = eff
    return ChapterOut(title=ch.title, wav=wav, cues=srtlib.renumber(cues), duration=audio.duration(wav), index=idx)


def _clone_convert(src: Path, profile: dict[str, Any], out: Path) -> Path:
    from . import clone  # lazy: heavy deps

    return clone.convert(src, profile, out)


# --------------------------------------------------------------------------------------
def run_tts(ctx: JobContext, req: TtsRequest) -> dict[str, Any]:
    if not ffmpeg.is_available():
        raise RuntimeError("FFmpeg chưa được cài. Vào Cài đặt → Tải FFmpeg.")
    if not req.chapters:
        raise RuntimeError("Không có nội dung để đọc")

    chapters = list(req.chapters)
    if req.export_mode == "range":
        a = max(1, req.range_start or 1)
        b = min(len(chapters), req.range_end or len(chapters))
        chapters = chapters[a - 1:b]
        if not chapters:
            raise RuntimeError("Khoảng chương không hợp lệ")

    base = Path(req.output_dir) if req.output_dir else settings.output_dir
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = base / f"{textlib.safe_filename(req.title)}_{stamp}"
    work = out_dir / ".work"
    work.mkdir(parents=True, exist_ok=True)

    total_units = sum(len(c.text) if not (c.cues and req.export_mode == "per_cue")
                      else sum(len(x.text) for x in c.cues) for c in chapters)
    prog = Progress(ctx, total_units)

    try:
        return _run_tts_inner(ctx, req, chapters, out_dir, work, prog)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        try:  # remove out_dir if nothing was produced (error/cancel before export)
            if out_dir.exists() and not any(out_dir.iterdir()):
                out_dir.rmdir()
        except OSError:
            pass


def _run_tts_inner(ctx: JobContext, req: TtsRequest, chapters: list[ChapterIn], out_dir: Path, work: Path,
                   prog: Progress) -> dict[str, Any]:
    chapter_outs: list[ChapterOut] = []
    for i, ch in enumerate(chapters, 1):
        ctx.check_cancelled()
        chapter_outs.append(synth_chapter(ctx, req, ch, work, i, prog))

    ctx.progress(0.96, "Đang xuất file...")
    outputs: list[Output] = []
    ext = f".{req.format}"

    def emit(name: str, wav: Path, cues: list[Cue]) -> Output:
        path = out_dir / f"{textlib.safe_filename(name)}{ext}"
        audio.encode(wav, path)
        srt_path = None
        if req.make_srt and cues:
            srt_path = path.with_suffix(".srt")
            srt_path.write_text(srtlib.to_srt(cues), encoding="utf-8")
        return Output(name=path.name, path=path, duration=audio.duration(path), srt=srt_path)

    def merge(group: list[ChapterOut], name: str) -> Output:
        if len(group) == 1:
            return emit(name, group[0].wav, group[0].cues)
        merged = work / f"{textlib.safe_filename(name)}_merged.wav"
        audio.concat([c.wav for c in group], merged, gap_ms=req.gap_ms)
        cues: list[Cue] = []
        t = 0.0
        for c in group:
            cues.extend(srtlib.shift(c.cues, t))
            t += c.duration + req.gap_ms / 1000.0
        return emit(name, merged, srtlib.renumber(cues))

    mode = req.export_mode
    if mode in ("per_chapter", "per_cue"):
        width = max(3, len(str(len(chapter_outs))))
        for c in chapter_outs:
            outputs.append(emit(f"{c.index:0{width}d} - {c.title}", c.wav, c.cues))
    elif mode == "merged":
        outputs.append(merge(chapter_outs, req.title))
    elif mode == "range":
        n = req.merge_every or 0
        if n and n > 0 and n < len(chapter_outs):
            for s in range(0, len(chapter_outs), n):
                group = chapter_outs[s:s + n]
                a, b = group[0].index, group[-1].index
                outputs.append(merge(group, f"{a:03d}-{b:03d} - {req.title}"))
        else:
            a, b = chapter_outs[0].index, chapter_outs[-1].index
            outputs.append(merge(chapter_outs, f"{req.title} ({a}-{b})"))
    else:
        raise RuntimeError(f"export_mode không hợp lệ: {mode}")

    m4b_path = None
    if req.make_m4b:
        ctx.progress(0.98, "Đang tạo M4B audiobook...")
        m4b_path = out_dir / f"{textlib.safe_filename(req.title)}.m4b"
        audio.make_m4b([c.wav for c in chapter_outs], [c.title for c in chapter_outs], m4b_path,
                       req.title, [c.duration for c in chapter_outs])
        outputs.append(Output(name=m4b_path.name, path=m4b_path, duration=sum(c.duration for c in chapter_outs),
                              kind="m4b"))

    zip_path = None
    if req.make_zip:
        ctx.progress(0.99, "Đang nén ZIP...")
        zip_path = out_dir / f"{textlib.safe_filename(req.title)}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for o in outputs:
                z.write(o.path, o.path.name)
                if o.srt:
                    z.write(o.srt, o.srt.name)

    return {
        "out_dir": str(out_dir),
        "outputs": [o.to_dict() for o in outputs],
        "zip": str(zip_path) if zip_path else None,
        "m4b": str(m4b_path) if m4b_path else None,
        "chapters": len(chapter_outs),
        "duration": round(sum(c.duration for c in chapter_outs), 2),
    }


# --------------------------------------------------------------------------------------
def preview(voice: str, text: str | None, out: Path) -> Path:
    """Short sample for the voice picker (cached by caller)."""
    if voice.startswith("clone:"):
        raise RuntimeError("Dùng trang Clone giọng để nghe thử voice profile")
    provider = _provider_for(voice)
    if not text:
        v = voices.find_voice(voice)
        text = voices.preview_text(v["lang"] if v else "en")
    raw = out.with_suffix(".raw.mp3")
    if provider == "tiktok":
        providers.synth_tiktok(text[:textlib.TIKTOK_MAX_CHARS], voice, raw, settings.get("tiktok_session_id", ""))
    else:
        providers.synth_edge(text, voice, raw)
    raw.replace(out)
    return out
