"""TTS providers: Microsoft Edge (edge-tts) and TikTok (unofficial API).

Each provider synthesises ONE chunk of text into an MP3 file and returns word timings
when available. Chunking, concatenation and effects live in tts_engine.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .srt import Word

log = logging.getLogger(__name__)


@dataclass
class SynthResult:
    audio_path: Path
    duration: float  # seconds (0 if unknown)
    words: list[Word] = field(default_factory=list)


class ProviderError(RuntimeError):
    pass


# ---- Edge -----------------------------------------------------------------------
def _pct(v: float) -> str:
    return f"{int(round((v - 1.0) * 100)):+d}%"


def _hz(semitones: float) -> str:
    # Edge accepts pitch as +/-Hz. Approx: 1 semitone ≈ 6% of ~200Hz ≈ 12Hz.
    return f"{int(round(semitones * 12)):+d}Hz"


async def _edge_async(text: str, voice: str, out: Path, rate: float, volume: float,
                      pitch_semitones: float) -> list[Word]:
    import edge_tts

    comm = edge_tts.Communicate(
        text, voice, rate=_pct(rate), volume=_pct(volume), pitch=_hz(pitch_semitones),
        boundary="WordBoundary",
    )
    words: list[Word] = []
    with open(out, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                dur = chunk["duration"] / 1e7
                words.append(Word(start=start, end=start + dur, text=chunk["text"]))
    return words


def synth_edge(text: str, voice: str, out: Path, rate: float = 1.0, volume: float = 1.0,
               pitch_semitones: float = 0.0, retries: int = 4) -> SynthResult:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            words = asyncio.run(_edge_async(text, voice, out, rate, volume, pitch_semitones))
            if not out.exists() or out.stat().st_size < 100:
                raise ProviderError("Edge trả về audio rỗng")
            dur = words[-1].end + 0.15 if words else 0.0
            return SynthResult(audio_path=out, duration=dur, words=words)
        except Exception as exc:  # noqa: BLE001
            last = exc
            log.warning("edge synth attempt %d failed: %s", attempt + 1, exc)
            time.sleep(1.5 * (attempt + 1))
    raise ProviderError(f"Edge TTS thất bại sau {retries} lần: {last}")


# ---- TikTok ---------------------------------------------------------------------
TIKTOK_ENDPOINTS = [
    "https://api16-normal-c-useast1a.tiktokv.com/media/api/text/speech/invoke/",
    "https://api22-normal-c-useast2a.tiktokv.com/media/api/text/speech/invoke/",
    "https://api16-normal-useast5.us.tiktokv.com/media/api/text/speech/invoke/",
]
_TIKTOK_UA = (
    "com.zhiliaoapp.musically/2022600030 (Linux; U; Android 7.1.2; es_ES; SM-G988N; "
    "Build/NRD90M;tt-ok/3.12.13.1)"
)
_TIKTOK_ERR = {
    1: "TikTok sessionid không hợp lệ hoặc hết hạn (Cài đặt → TikTok sessionid).",
    2: "Đoạn văn quá dài cho TikTok (tối đa ~300 ký tự).",
    4: "Giọng TikTok không hợp lệ.",
    5: "TikTok yêu cầu sessionid.",
}


def synth_tiktok(text: str, voice: str, out: Path, session_id: str, retries: int = 3) -> SynthResult:
    if not session_id:
        raise ProviderError(_TIKTOK_ERR[5])
    text = text.replace("+", "plus").replace("&", "and").strip()
    params = {"text_speaker": voice, "req_text": text, "speaker_map_type": "0", "aid": "1233"}
    headers = {"User-Agent": _TIKTOK_UA, "Cookie": f"sessionid={session_id}"}
    last: Exception | None = None
    for attempt in range(retries):
        url = TIKTOK_ENDPOINTS[attempt % len(TIKTOK_ENDPOINTS)]
        try:
            r = httpx.post(url, params=params, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json()
            code = data.get("status_code", -1)
            if code != 0:
                msg = _TIKTOK_ERR.get(code, f"TikTok lỗi {code}: {data.get('message') or data.get('status_msg')}")
                if code in (1, 4, 5):
                    raise ProviderError(msg)
                raise RuntimeError(msg)
            b64 = data["data"]["v_str"]
            out.write_bytes(base64.b64decode(b64))
            dur = float(data["data"].get("duration") or 0) / 1000.0
            return SynthResult(audio_path=out, duration=dur, words=[])
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            last = exc
            log.warning("tiktok synth attempt %d failed: %s", attempt + 1, exc)
            time.sleep(1.0 * (attempt + 1))
    raise ProviderError(f"TikTok TTS thất bại: {last}")
