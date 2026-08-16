"""Voice catalog: Microsoft Edge Neural voices (live list, cached) + TikTok voices (static)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from ..config import CACHE_DIR

log = logging.getLogger(__name__)

EDGE_CACHE = CACHE_DIR / "edge_voices.json"
EDGE_CACHE_TTL = 7 * 24 * 3600

# Language → display + emoji (used by UI filter chips)
LANG_META: dict[str, dict[str, str]] = {
    "vi": {"name": "Tiếng Việt", "flag": "🇻🇳"},
    "en": {"name": "English", "flag": "🇺🇸"},
    "zh": {"name": "Trung", "flag": "🇨🇳"},
    "ja": {"name": "Nhật", "flag": "🇯🇵"},
    "ko": {"name": "Hàn", "flag": "🇰🇷"},
    "th": {"name": "Thái", "flag": "🇹🇭"},
    "fr": {"name": "Pháp", "flag": "🇫🇷"},
    "de": {"name": "Đức", "flag": "🇩🇪"},
    "es": {"name": "Tây Ban Nha", "flag": "🇪🇸"},
    "pt": {"name": "Bồ Đào Nha", "flag": "🇵🇹"},
    "ru": {"name": "Nga", "flag": "🇷🇺"},
    "id": {"name": "Indonesia", "flag": "🇮🇩"},
    "it": {"name": "Ý", "flag": "🇮🇹"},
    "hi": {"name": "Hindi", "flag": "🇮🇳"},
    "ar": {"name": "Ả Rập", "flag": "🇸🇦"},
}

HOT_VOICES = {
    "vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural", "en-US-JennyNeural", "en-US-GuyNeural",
    "en-US-AriaNeural", "zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "ja-JP-NanamiNeural",
    "ko-KR-SunHiNeural", "BV074_streaming", "en_us_001",
}

# TikTok voice ids (unofficial API). Names in Vietnamese where sensible.
TIKTOK_VOICES: list[dict[str, Any]] = [
    {"id": "BV074_streaming", "name": "Cô Gái Hoạt Ngôn", "locale": "vi-VN", "gender": "female"},
    {"id": "BV075_streaming", "name": "Nam Việt Nam", "locale": "vi-VN", "gender": "male"},
    {"id": "en_us_001", "name": "Nữ English (US)", "locale": "en-US", "gender": "female"},
    {"id": "en_us_006", "name": "Nam English (US) 1", "locale": "en-US", "gender": "male"},
    {"id": "en_us_007", "name": "Nam English (US) 2", "locale": "en-US", "gender": "male"},
    {"id": "en_us_009", "name": "Nam English (US) 3", "locale": "en-US", "gender": "male"},
    {"id": "en_us_010", "name": "Nam English (US) 4", "locale": "en-US", "gender": "male"},
    {"id": "en_uk_001", "name": "Nam English (UK) 1", "locale": "en-GB", "gender": "male"},
    {"id": "en_uk_003", "name": "Nam English (UK) 2", "locale": "en-GB", "gender": "male"},
    {"id": "en_au_001", "name": "Nữ English (AU)", "locale": "en-AU", "gender": "female"},
    {"id": "en_au_002", "name": "Nam English (AU)", "locale": "en-AU", "gender": "male"},
    {"id": "en_female_emotional", "name": "Nữ Peaceful", "locale": "en-US", "gender": "female"},
    {"id": "en_male_narration", "name": "Nam Narrator", "locale": "en-US", "gender": "male"},
    {"id": "en_male_funny", "name": "Nam Wacky", "locale": "en-US", "gender": "male"},
    {"id": "en_us_ghostface", "name": "Ghostface", "locale": "en-US", "gender": "male"},
    {"id": "en_us_c3po", "name": "C3PO", "locale": "en-US", "gender": "male"},
    {"id": "en_us_stitch", "name": "Stitch", "locale": "en-US", "gender": "male"},
    {"id": "en_us_rocket", "name": "Rocket", "locale": "en-US", "gender": "male"},
    {"id": "en_female_f08_salut_damour", "name": "Alto (hát)", "locale": "en-US", "gender": "female"},
    {"id": "en_male_m03_lobby", "name": "Tenor (hát)", "locale": "en-US", "gender": "male"},
    {"id": "kr_002", "name": "Nam Hàn Quốc 1", "locale": "ko-KR", "gender": "male"},
    {"id": "kr_003", "name": "Nữ Hàn Quốc", "locale": "ko-KR", "gender": "female"},
    {"id": "kr_004", "name": "Nam Hàn Quốc 2", "locale": "ko-KR", "gender": "male"},
    {"id": "jp_001", "name": "Nữ Nhật 1", "locale": "ja-JP", "gender": "female"},
    {"id": "jp_003", "name": "Nữ Nhật 2", "locale": "ja-JP", "gender": "female"},
    {"id": "jp_005", "name": "Nữ Nhật 3", "locale": "ja-JP", "gender": "female"},
    {"id": "jp_006", "name": "Nam Nhật", "locale": "ja-JP", "gender": "male"},
    {"id": "fr_001", "name": "Nam Pháp 1", "locale": "fr-FR", "gender": "male"},
    {"id": "fr_002", "name": "Nam Pháp 2", "locale": "fr-FR", "gender": "male"},
    {"id": "de_001", "name": "Nữ Đức", "locale": "de-DE", "gender": "female"},
    {"id": "de_002", "name": "Nam Đức", "locale": "de-DE", "gender": "male"},
    {"id": "es_002", "name": "Nam Tây Ban Nha", "locale": "es-ES", "gender": "male"},
    {"id": "es_mx_002", "name": "Nam Mexico", "locale": "es-MX", "gender": "male"},
    {"id": "br_001", "name": "Nữ Brazil 1", "locale": "pt-BR", "gender": "female"},
    {"id": "br_003", "name": "Nữ Brazil 2", "locale": "pt-BR", "gender": "female"},
    {"id": "br_005", "name": "Nam Brazil", "locale": "pt-BR", "gender": "male"},
    {"id": "id_001", "name": "Nữ Indonesia", "locale": "id-ID", "gender": "female"},
]

_EMOJI = {"vi": "🎀", "en": "🎙️", "zh": "🏮", "ja": "🌸", "ko": "🎎", "th": "🌺"}


def _lang_of(locale: str) -> str:
    return (locale or "").split("-")[0].lower()


def _pretty_edge_name(short_name: str) -> str:
    base = short_name.split("-")[-1]
    return base.replace("Neural", " Neural").replace("Multilingual", " Multilingual").strip()


def _to_voice(raw: dict[str, Any], provider: str) -> dict[str, Any]:
    locale = raw.get("locale") or raw.get("Locale") or ""
    lang = _lang_of(locale)
    vid = raw.get("id") or raw.get("ShortName")
    gender = (raw.get("gender") or raw.get("Gender") or "unknown").lower()
    return {
        "id": vid,
        "name": raw.get("name") or _pretty_edge_name(vid),
        "provider": provider,
        "locale": locale,
        "lang": lang,
        "gender": gender if gender in ("female", "male") else "unknown",
        "hot": vid in HOT_VOICES,
        "emoji": _EMOJI.get(lang, "🌍"),
    }


async def _fetch_edge() -> list[dict[str, Any]]:
    import edge_tts

    return await edge_tts.list_voices()


def edge_voices(force: bool = False) -> list[dict[str, Any]]:
    if not force and EDGE_CACHE.exists() and time.time() - EDGE_CACHE.stat().st_mtime < EDGE_CACHE_TTL:
        try:
            return json.loads(EDGE_CACHE.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        raw = asyncio.run(_fetch_edge())
        voices = [_to_voice(v, "edge") for v in raw]
        EDGE_CACHE.write_text(json.dumps(voices, ensure_ascii=False), encoding="utf-8")
        return voices
    except Exception as exc:  # offline: use stale cache or built-in minimal list
        log.warning("edge voice list failed: %s", exc)
        if EDGE_CACHE.exists():
            return json.loads(EDGE_CACHE.read_text(encoding="utf-8"))
        return [_to_voice({"ShortName": v, "Locale": "-".join(v.split("-")[:2]), "Gender": g}, "edge")
                for v, g in [("vi-VN-HoaiMyNeural", "Female"), ("vi-VN-NamMinhNeural", "Male"),
                             ("en-US-JennyNeural", "Female"), ("en-US-GuyNeural", "Male")]]


def tiktok_voices() -> list[dict[str, Any]]:
    return [_to_voice(v, "tiktok") for v in TIKTOK_VOICES]


_PRIORITY_LANGS = ["vi", "en", "zh", "ja", "ko", "th", "fr", "de", "es", "pt", "ru", "id"]


def all_voices(force: bool = False) -> list[dict[str, Any]]:
    voices = edge_voices(force) + tiktok_voices()

    def key(v: dict[str, Any]) -> tuple:
        lang_rank = _PRIORITY_LANGS.index(v["lang"]) if v["lang"] in _PRIORITY_LANGS else 99
        return (lang_rank, not v["hot"], v["locale"], v["provider"] != "edge", v["name"])

    return sorted(voices, key=key)


def find_voice(voice_id: str) -> dict[str, Any] | None:
    for v in all_voices():
        if v["id"] == voice_id:
            return v
    return None


def provider_of(voice_id: str) -> str:
    if voice_id.startswith("clone:"):
        return "clone"
    if any(v["id"] == voice_id for v in TIKTOK_VOICES):
        return "tiktok"
    return "edge"


PREVIEW_TEXT: dict[str, str] = {
    "vi": "Xin chào, đây là giọng đọc mẫu. Chúc bạn một ngày tốt lành!",
    "en": "Hello, this is a sample of my voice. Have a wonderful day!",
    "zh": "你好，这是我的声音示例。祝你有美好的一天！",
    "ja": "こんにちは、これは私の声のサンプルです。良い一日を！",
    "ko": "안녕하세요, 제 목소리 샘플입니다. 좋은 하루 되세요!",
    "th": "สวัสดีค่ะ นี่คือตัวอย่างเสียงของฉัน ขอให้เป็นวันที่ดี",
    "fr": "Bonjour, ceci est un exemple de ma voix. Bonne journée !",
    "de": "Hallo, das ist eine Probe meiner Stimme. Einen schönen Tag!",
    "es": "Hola, esta es una muestra de mi voz. ¡Que tengas un buen día!",
}


def preview_text(lang: str) -> str:
    return PREVIEW_TEXT.get(lang, PREVIEW_TEXT["en"])
