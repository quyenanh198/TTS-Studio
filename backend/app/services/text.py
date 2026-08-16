"""Text normalisation, sentence splitting and chunking for TTS."""

from __future__ import annotations

import re
import unicodedata

# Sentence terminators incl. CJK + Vietnamese-friendly punctuation.
_SENT_END = r"[.!?…。！？]+[\"'”’)\]]*"
_SENT_RE = re.compile(rf"(.+?{_SENT_END})(\s+|$)|(.+?)(\n+|$)", re.S)
_WS_RE = re.compile(r"[ \t ]+")
_MULTI_NL = re.compile(r"\n{3,}")

MAX_CHUNK_CHARS = 2500  # Edge handles long input, but shorter chunks = better progress + retry.
TIKTOK_MAX_CHARS = 280


def normalize(text: str) -> str:
    """Normalise unicode, whitespace, quotes; keep paragraph breaks."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", "\n").replace(" ", "\n\n").replace("﻿", "")
    # de-hyphenate line-broken words (PDF): "trans-\nform" -> "transform"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    """Split into sentences; paragraph breaks always split."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        # join soft line breaks inside a paragraph
        para = re.sub(r"\s*\n\s*", " ", para)
        for m in _SENT_RE.finditer(para):
            s = (m.group(1) or m.group(3) or "").strip()
            if s:
                out.append(s)
    return out


def chunk_sentences(sentences: list[str], max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Greedy pack sentences into chunks ≤ max_chars. Over-long sentences are hard-split."""
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for s in sentences:
        if len(s) > max_chars:
            if buf:
                chunks.append(" ".join(buf))
                buf, size = [], 0
            chunks.extend(_hard_split(s, max_chars))
            continue
        if size + len(s) + 1 > max_chars and buf:
            chunks.append(" ".join(buf))
            buf, size = [], 0
        buf.append(s)
        size += len(s) + 1
    if buf:
        chunks.append(" ".join(buf))
    return chunks


def _hard_split(s: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    while len(s) > max_chars:
        cut = max(s.rfind(",", 0, max_chars), s.rfind(";", 0, max_chars), s.rfind(" ", 0, max_chars))
        if cut < max_chars // 2:
            cut = max_chars
        parts.append(s[:cut].strip())
        s = s[cut:].strip()
    if s:
        parts.append(s)
    return parts


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    return chunk_sentences(split_sentences(normalize(text)), max_chars)


def safe_filename(name: str, max_len: int = 80) -> str:
    name = unicodedata.normalize("NFC", name or "").strip()
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name[:max_len] or "untitled").rstrip(" .")
