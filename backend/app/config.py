"""Application paths and settings.

All user data (settings, DB, models, outputs) lives under APP_DATA_DIR so the
program folder itself can be read-only / portable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

APP_NAME = "TTSStudio"


def _default_data_dir() -> Path:
    env = os.environ.get("TTS_STUDIO_DATA")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path.home() / ".local" / "share"
    return base / APP_NAME


def _program_dir() -> Path:
    # backend/app/config.py -> project root
    return Path(__file__).resolve().parents[2]


PROGRAM_DIR = _program_dir()
DATA_DIR = _default_data_dir()
OUTPUT_DIR = DATA_DIR / "output"
MODELS_DIR = DATA_DIR / "models"
CACHE_DIR = DATA_DIR / "cache"
BIN_DIR = DATA_DIR / "bin"
PROFILES_DIR = DATA_DIR / "voices"
DB_PATH = DATA_DIR / "studio.sqlite3"
SETTINGS_PATH = DATA_DIR / "settings.json"
FRONTEND_DIST = PROGRAM_DIR / "frontend" / "dist"

for _d in (DATA_DIR, OUTPUT_DIR, MODELS_DIR, CACHE_DIR, BIN_DIR, PROFILES_DIR):
    _d.mkdir(parents=True, exist_ok=True)


DEFAULT_SETTINGS: dict[str, Any] = {
    "output_dir": str(OUTPUT_DIR),
    "tiktok_session_id": "",
    "default_voice": "vi-VN-HoaiMyNeural",
    "default_format": "mp3",
    "default_rate": 1.0,
    "default_volume": 1.0,
    "keep_pitch": True,
    "asr_model": "small",
    "asr_device": "auto",
    "vc_device": "auto",
    "vc_steps": 0,  # 0 = auto (25 GPU / 10 CPU); 10 fast … 50 best
    "concurrency": 2,
    "language_ui": "vi",
}


class Settings:
    """Tiny JSON-backed settings store (no external deps)."""

    def __init__(self, path: Path = SETTINGS_PATH):
        self.path = path
        self._data: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                self._data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:
                pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        for k, v in values.items():
            if k in DEFAULT_SETTINGS:
                self._data[k] = v
        self.save()
        return dict(self._data)

    def all(self) -> dict[str, Any]:
        return dict(self._data)

    @property
    def output_dir(self) -> Path:
        p = Path(self.get("output_dir") or OUTPUT_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
