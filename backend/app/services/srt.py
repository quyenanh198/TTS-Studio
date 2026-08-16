"""Subtitle helpers: cue model, SRT/VTT/LRC serialisation, word→cue grouping, parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Cue:
    start: float  # seconds
    end: float
    text: str
    index: int = 0

    def to_dict(self) -> dict:
        return {"index": self.index, "start": round(self.start, 3), "end": round(self.end, 3), "text": self.text}


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    """A timed piece of text, optionally with word timings (ASR)."""

    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


def fmt_srt_time(t: float) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt_vtt_time(t: float) -> str:
    return fmt_srt_time(t).replace(",", ".")


def fmt_lrc_time(t: float) -> str:
    t = max(0.0, t)
    m = int(t // 60)
    s = t - m * 60
    return f"[{m:02d}:{s:05.2f}]"


def to_srt(cues: list[Cue]) -> str:
    out = []
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{fmt_srt_time(c.start)} --> {fmt_srt_time(c.end)}\n{c.text.strip()}\n")
    return "\n".join(out)


def to_vtt(cues: list[Cue]) -> str:
    out = ["WEBVTT", ""]
    for c in cues:
        out.append(f"{fmt_vtt_time(c.start)} --> {fmt_vtt_time(c.end)}\n{c.text.strip()}\n")
    return "\n".join(out)


def to_lrc(cues: list[Cue], title: str = "") -> str:
    out = []
    if title:
        out.append(f"[ti:{title}]")
    for c in cues:
        out.append(f"{fmt_lrc_time(c.start)}{c.text.strip()}")
    return "\n".join(out) + "\n"


def to_txt(cues: list[Cue]) -> str:
    return "\n".join(c.text.strip() for c in cues) + "\n"


_TIME_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _parse_time(s: str) -> float:
    m = _TIME_RE.search(s)
    if not m:
        raise ValueError(f"bad timestamp: {s}")
    h, mi, se, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(se) + int(ms.ljust(3, "0")[:3]) / 1000


def parse_srt(content: str) -> list[Cue]:
    """Lenient SRT parser (handles BOM, CRLF, missing indices, HTML tags)."""
    content = content.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        ti = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if ti is None:
            continue
        a, b = lines[ti].split("-->")[:2]
        text = " ".join(lines[ti + 1:]).strip()
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\{\\[^}]*\}", "", text)  # ASS tags
        if not text:
            continue
        cues.append(Cue(start=_parse_time(a), end=_parse_time(b), text=text, index=len(cues) + 1))
    return cues


def read_srt(path: str | Path) -> list[Cue]:
    raw = Path(path).read_bytes()
    try:
        return parse_srt(raw.decode("utf-8"))
    except UnicodeDecodeError:
        import chardet

        enc = chardet.detect(raw).get("encoding") or "utf-8"
        return parse_srt(raw.decode(enc, errors="replace"))


# ---- punctuation re-alignment -------------------------------------------------------
_STRIP_PUNCT = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)


def _core(tok: str) -> str:
    return _STRIP_PUNCT.sub("", tok).lower()


def attach_punctuation(text: str, words: list[Word]) -> list[Word]:
    """Edge word boundaries strip punctuation; restore it from the source text so cue
    grouping can split at sentence ends. Greedy alignment with small lookahead."""
    tokens = text.split()
    out: list[Word] = []
    ti = 0
    for w in words:
        wc = _core(w.text)
        matched = None
        for look in range(0, 4):
            if ti + look >= len(tokens):
                break
            tc = _core(tokens[ti + look])
            if tc == wc or (wc and tc.startswith(wc)) or (tc and wc.startswith(tc)):
                matched = ti + look
                break
        if matched is not None:
            tok = tokens[matched]
            # if boundary word is a prefix of a longer token (e.g. hyphenated), keep boundary text but
            # carry trailing punctuation only when it's a full match
            new_text = tok if _core(tok) == wc else w.text
            out.append(Word(w.start, w.end, new_text))
            ti = matched + (1 if _core(tok) == wc else 0)
        else:
            out.append(w)
    return out


# ---- word grouping -------------------------------------------------------------
_END_PUNCT = re.compile(r"[.!?…。！？]+[\"'”’)\]]*$")
_MID_PUNCT = re.compile(r"[,;:，；：]$")


def words_to_cues(
    words: list[Word],
    max_chars: int = 84,
    max_duration: float = 6.0,
    max_gap: float = 0.8,
) -> list[Cue]:
    """Group timed words into readable subtitle cues."""
    cues: list[Cue] = []
    buf: list[Word] = []

    def flush() -> None:
        if not buf:
            return
        text = " ".join(w.text for w in buf).strip()
        # collapse space before punctuation
        text = re.sub(r"\s+([,.!?;:…])", r"\1", text)
        cues.append(Cue(start=buf[0].start, end=buf[-1].end, text=text, index=len(cues) + 1))
        buf.clear()

    for w in words:
        if buf:
            cur_len = sum(len(x.text) + 1 for x in buf)
            gap = w.start - buf[-1].end
            too_long = cur_len + len(w.text) > max_chars
            too_slow = w.end - buf[0].start > max_duration
            if gap > max_gap or too_long or too_slow:
                flush()
        buf.append(w)
        if _END_PUNCT.search(w.text):
            flush()
        elif _MID_PUNCT.search(w.text) and sum(len(x.text) + 1 for x in buf) > max_chars * 0.6:
            flush()
    flush()
    # ensure monotonic + min duration
    for i, c in enumerate(cues):
        if c.end - c.start < 0.3:
            c.end = c.start + 0.3
        if i + 1 < len(cues) and c.end > cues[i + 1].start:
            c.end = cues[i + 1].start
    return cues


def shift(cues: list[Cue], offset: float) -> list[Cue]:
    return [Cue(start=c.start + offset, end=c.end + offset, text=c.text, index=c.index) for c in cues]


def scale(cues: list[Cue], factor: float) -> list[Cue]:
    return [Cue(start=c.start * factor, end=c.end * factor, text=c.text, index=c.index) for c in cues]


def renumber(cues: list[Cue]) -> list[Cue]:
    for i, c in enumerate(cues, 1):
        c.index = i
    return cues
