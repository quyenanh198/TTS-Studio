"""Input endpoints: parse pasted text or uploaded ebook/subtitle files into a Book."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..config import CACHE_DIR
from ..services import parsers
from ..services.text import safe_filename

router = APIRouter()
UPLOAD_DIR = CACHE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class TextBody(BaseModel):
    text: str
    title: str | None = None


@router.post("/inputs/text")
def parse_text(body: TextBody) -> dict[str, Any]:
    if not body.text.strip():
        raise HTTPException(422, "Văn bản trống")
    return parsers.parse_plain(body.text, body.title or "Văn bản").to_dict()


@router.post("/inputs/file")
async def parse_file(file: UploadFile = File(...)) -> dict[str, Any]:
    name = Path(file.filename or "upload").name
    ext = Path(name).suffix.lower()
    if ext not in parsers.SUPPORTED:
        raise HTTPException(415, f"Định dạng không hỗ trợ: {ext}. Hỗ trợ: {', '.join(sorted(parsers.SUPPORTED))}")
    dest = UPLOAD_DIR / f"{int(time.time())}_{safe_filename(Path(name).stem)}{ext}"
    with open(dest, "wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)
    try:
        book = await run_in_threadpool(parsers.parse_file, dest)  # PDF/EPUB parsing is CPU-bound
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Không đọc được file: {exc}") from exc
    return book.to_dict()


@router.get("/inputs/formats")
def formats() -> list[str]:
    return sorted(parsers.SUPPORTED)
