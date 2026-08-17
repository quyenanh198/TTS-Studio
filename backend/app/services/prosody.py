"""Expressive prosody planning ("giọng có hồn").

Edge TTS has no emotion styles on the free endpoint, but it does honour per-request rate / pitch /
volume. We approximate expressiveness by reading the *context* of each sentence — questions,
exclamations, dialogue, trailing thoughts, emotional vocabulary, paragraph boundaries — and giving
each sentence a small prosody offset plus natural pauses. Offsets are deliberately gentle
(Vietnamese is tonal: large pitch swings distort word tones); `level` scales them 0..1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- emotional vocabulary (vi + en, lowercase, matched on word boundaries) -------------------
_SAD = ("buồn", "khóc", "nước mắt", "đau", "mất", "chết", "tuyệt vọng", "cô đơn", "thở dài", "nghẹn",
        "tiếc", "xót", "lặng", "sad", "cry", "cried", "tears", "grief", "lonely", "sorrow", "sigh")
_JOY = ("vui", "cười", "hạnh phúc", "tuyệt vời", "sung sướng", "hân hoan", "reo", "phấn khích", "yêu",
        "happy", "laugh", "joy", "wonderful", "excited", "love", "delight", "cheer")
_ANGER = ("giận", "tức", "quát", "hét", "gào", "điên", "căm", "phẫn nộ", "gắt", "angry", "furious",
          "shout", "yell", "scream", "rage", "damn")
_FEAR = ("sợ", "hoảng", "run", "kinh hoàng", "rùng mình", "hãi", "afraid", "fear", "terrified", "panic",
         "tremble", "horror")
_CALM = ("nhẹ nhàng", "êm", "bình yên", "thì thầm", "khẽ", "dịu", "gentle", "softly", "whisper", "calm",
         "quiet", "peaceful")

_QUOTE_START = re.compile(r'^\s*[\"“„«‘\'\-–—]')
_QUOTE_ANY = re.compile(r'[\"“”„«»]')


@dataclass
class Segment:
    text: str
    rate: float = 0.0        # relative delta, e.g. +0.05 = 5% faster
    pitch: float = 0.0       # semitones
    volume: float = 0.0      # relative delta
    pause_after: float = 0.0  # seconds of silence after this segment
    tags: list[str] = field(default_factory=list)


def _has(text: str, words: tuple[str, ...]) -> bool:
    t = text.lower()
    return any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", t) for w in words)


def classify(sentence: str, paragraph_end: bool = False, in_dialogue: bool = False) -> Segment:
    s = sentence.strip()
    seg = Segment(text=s)
    r = p = v = 0.0
    pause = 0.0
    core = s.rstrip('"”’\')»]')  # terminal punctuation may sit before a closing quote/bracket

    if core.endswith(("?", "？")):
        p += 0.6; r -= 0.03; seg.tags.append("question")
    if core.endswith(("!", "！")):
        r += 0.05; v += 0.15; p += 0.4; seg.tags.append("exclaim")
    if core.endswith(("…", "...")):
        r -= 0.08; p -= 0.3; pause += 0.35; seg.tags.append("trailing")
    if in_dialogue or _QUOTE_START.match(s) or _QUOTE_ANY.search(s):
        p += 0.5; r += 0.02; seg.tags.append("dialogue")

    if _has(s, _SAD):
        p -= 0.5; r -= 0.07; v -= 0.05; pause += 0.2; seg.tags.append("sad")
    elif _has(s, _ANGER):
        r += 0.08; v += 0.18; p += 0.3; seg.tags.append("anger")
    elif _has(s, _FEAR):
        r += 0.04; p += 0.4; v -= 0.03; seg.tags.append("fear")
    elif _has(s, _JOY):
        p += 0.5; r += 0.04; v += 0.06; seg.tags.append("joy")
    elif _has(s, _CALM):
        r -= 0.05; v -= 0.08; p -= 0.2; seg.tags.append("calm")

    if len(s) > 160:  # long narrative sentence: ease off slightly for clarity
        r -= 0.02
    if paragraph_end:
        pause += 0.45; seg.tags.append("para")

    # clamp — keep it subtle
    seg.rate = max(-0.12, min(0.12, r))
    seg.pitch = max(-1.2, min(1.2, p))
    seg.volume = max(-0.15, min(0.25, v))
    seg.pause_after = min(0.9, pause)
    return seg


def plan(paragraphs: list[list[str]], level: float = 0.7) -> list[Segment]:
    """paragraphs: list of paragraphs, each a list of sentences. Returns one Segment per sentence with
    prosody deltas scaled by `level` (0 = flat, 1 = full)."""
    level = max(0.0, min(1.0, level))
    out: list[Segment] = []
    for para in paragraphs:
        open_quote = False
        for i, sent in enumerate(para):
            seg = classify(sent, paragraph_end=(i == len(para) - 1), in_dialogue=open_quote)
            # track running dialogue across sentences within a paragraph
            q = len(_QUOTE_ANY.findall(sent))
            if q % 2 == 1:
                open_quote = not open_quote
            seg.rate *= level
            seg.pitch *= level
            seg.volume *= level
            seg.pause_after *= max(0.4, level)
            out.append(seg)
    return out


def group(segments: list[Segment], max_chars: int) -> list[Segment]:
    """Merge consecutive sentences with (near-)identical prosody into bigger requests to keep the
    number of TTS calls low. A pause or a prosody change starts a new group."""
    groups: list[Segment] = []
    for seg in segments:
        if groups:
            g = groups[-1]
            same = (abs(g.rate - seg.rate) < 0.015 and abs(g.pitch - seg.pitch) < 0.15
                    and abs(g.volume - seg.volume) < 0.03 and g.pause_after == 0.0)
            if same and len(g.text) + len(seg.text) + 1 <= max_chars:
                g.text = f"{g.text} {seg.text}"
                g.pause_after = seg.pause_after
                g.tags = sorted(set(g.tags) | set(seg.tags))
                continue
        groups.append(Segment(seg.text, seg.rate, seg.pitch, seg.volume, seg.pause_after, list(seg.tags)))
    return groups
