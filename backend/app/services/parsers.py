"""Input parsers → Book{chapters}. Supports TXT/MD, EPUB, PDF, DOCX, SRT (+ MOBI/AZW3 via calibre)."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import srt as srtlib
from .text import normalize

log = logging.getLogger(__name__)


@dataclass
class Chapter:
    title: str
    text: str
    cues: list[dict[str, Any]] | None = None

    def to_dict(self, index: int) -> dict[str, Any]:
        return {"index": index, "title": self.title, "text": self.text, "chars": len(self.text),
                "cues": self.cues}


@dataclass
class Book:
    title: str
    source: str
    format: str
    chapters: list[Chapter] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "format": self.format,
            "chapters": [c.to_dict(i + 1) for i, c in enumerate(self.chapters)],
            "total_chars": sum(len(c.text) for c in self.chapters),
        }


# ---- chapter heading heuristics ----------------------------------------------------
_HEADING_RES = [
    re.compile(r"^\s*(chương|chuong|chapter|chap\.?|hồi|quyển|phần|part|tập|book)\s*[\d一二三四五六七八九十百千IVXLC]+[^\n]{0,80}$", re.I),
    re.compile(r"^\s*第\s*[\d一二三四五六七八九十百千零〇]+\s*[章回节節卷部集话話][^\n]{0,80}$"),
    re.compile(r"^\s*(prologue|epilogue|mở đầu|lời nói đầu|kết thúc|ngoại truyện|phiên ngoại)[^\n]{0,60}$", re.I),
    re.compile(r"^\s*\d{1,4}\s*[.:\-–—]\s*\S[^\n]{0,80}$"),
]
MIN_CHAPTER_CHARS = 200
MAX_CHAPTER_CHARS = 60_000  # split huge chapters for progress granularity


def is_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 100:
        return False
    return any(r.match(line) for r in _HEADING_RES)


def split_by_headings(text: str, default_title: str = "Nội dung") -> list[Chapter]:
    lines = text.split("\n")
    heads = [i for i, ln in enumerate(lines) if is_heading(ln)]
    # need at least 2 headings to trust the pattern
    if len(heads) < 2:
        return _split_long([Chapter(default_title, text.strip())])
    chapters: list[Chapter] = []
    pre = "\n".join(lines[:heads[0]]).strip()
    if len(pre) >= MIN_CHAPTER_CHARS:
        chapters.append(Chapter("Mở đầu", pre))
    for j, h in enumerate(heads):
        end = heads[j + 1] if j + 1 < len(heads) else len(lines)
        title = lines[h].strip()
        body = "\n".join(lines[h + 1:end]).strip()
        if not body:
            continue  # heading immediately followed by another heading
        chapters.append(Chapter(title, body))
    return _split_long(chapters or [Chapter(default_title, text.strip())])


def _split_long(chapters: list[Chapter]) -> list[Chapter]:
    out: list[Chapter] = []
    for c in chapters:
        if len(c.text) <= MAX_CHAPTER_CHARS:
            out.append(c)
            continue
        paras = c.text.split("\n\n")
        buf: list[str] = []
        size = 0
        part = 1
        for p in paras:
            if size + len(p) > MAX_CHAPTER_CHARS and buf:
                out.append(Chapter(f"{c.title} (phần {part})", "\n\n".join(buf)))
                part += 1
                buf, size = [], 0
            buf.append(p)
            size += len(p) + 2
        if buf:
            out.append(Chapter(f"{c.title} (phần {part})" if part > 1 else c.title, "\n\n".join(buf)))
    return out


# ---- format readers ----------------------------------------------------------------
def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    import chardet

    enc = chardet.detect(raw).get("encoding") or "utf-8"
    return raw.decode(enc, errors="replace")


def parse_plain(text: str, title: str) -> Book:
    text = normalize(text)
    # strip markdown heading markers but keep the line as heading candidate
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    return Book(title=title, source="text", format="txt", chapters=split_by_headings(text))


def parse_srt_file(path: Path) -> Book:
    cues = srtlib.read_srt(path)
    if not cues:
        raise ValueError("File SRT không có phụ đề hợp lệ")
    text = "\n".join(c.text for c in cues)
    ch = Chapter(path.stem, text, cues=[c.to_dict() for c in cues])
    return Book(title=path.stem, source=str(path), format="srt", chapters=[ch])


def parse_epub(path: Path) -> Book:
    import warnings

    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    from ebooklib import ITEM_DOCUMENT, epub

    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    book = epub.read_epub(str(path), options={"ignore_ncx": False})
    title = (book.get_metadata("DC", "title") or [[path.stem]])[0][0] or path.stem

    toc_titles: dict[str, str] = {}

    def walk(items):
        for it in items:
            if isinstance(it, (list, tuple)):
                walk(it)
            elif hasattr(it, "href"):
                toc_titles.setdefault(it.href.split("#")[0], it.title)
            elif hasattr(it, "title") and hasattr(it, "items"):  # Section
                walk(it.items)

    walk(book.toc)

    chapters: list[Chapter] = []
    for item_id, _linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ITEM_DOCUMENT:
            continue
        soup = BeautifulSoup(item.get_content(), "lxml")
        for t in soup(["script", "style", "nav", "sup"]):
            t.decompose()
        heading = None
        for tag in ("h1", "h2", "h3", "title"):
            h = soup.find(tag)
            if h and h.get_text(strip=True):
                heading = h.get_text(" ", strip=True)
                break
        blocks = []
        body = soup.body or soup
        for el in body.find_all(["p", "h1", "h2", "h3", "h4", "li", "blockquote", "div"]):
            if el.find(["p", "div"]):  # container; children will be visited
                continue
            txt = el.get_text(" ", strip=True)
            if txt:
                blocks.append(txt)
        text = normalize("\n\n".join(blocks)) if blocks else normalize(body.get_text("\n", strip=True))
        if len(text) < 20:
            continue
        name = toc_titles.get(item.get_name()) or heading or f"Phần {len(chapters) + 1}"
        chapters.append(Chapter(name, text))
    if not chapters:
        raise ValueError("EPUB không có nội dung văn bản")
    if len(chapters) == 1 and len(chapters[0].text) > MAX_CHAPTER_CHARS // 2:
        chapters = split_by_headings(chapters[0].text, chapters[0].title)
    return Book(title=title, source=str(path), format="epub", chapters=_split_long(chapters))


def parse_pdf(path: Path) -> Book:
    import fitz  # pymupdf

    doc = fitz.open(str(path))
    title = (doc.metadata or {}).get("title") or path.stem
    pages = [p.get_text("text") for p in doc]
    toc = doc.get_toc(simple=True)  # [level, title, page]
    chapters: list[Chapter] = []
    if toc:
        entries = [(t, max(1, pg)) for lvl, t, pg in toc if lvl <= 2 and pg > 0]
        entries.sort(key=lambda x: x[1])
        for i, (t, pg) in enumerate(entries):
            end = entries[i + 1][1] - 1 if i + 1 < len(entries) else len(pages)
            body = "\n".join(pages[pg - 1:end]) if end >= pg else pages[pg - 1]
            body = _clean_pdf(body)
            if len(body) >= 50:
                chapters.append(Chapter(t.strip() or f"Phần {i + 1}", body))
    if not chapters:
        chapters = split_by_headings(_clean_pdf("\n".join(pages)), title)
    return Book(title=title, source=str(path), format="pdf", chapters=chapters)


_PAGE_NUM = re.compile(r"^\s*(trang\s*)?\d{1,4}\s*$", re.I | re.M)


def _clean_pdf(text: str) -> str:
    text = _PAGE_NUM.sub("", text)
    # rejoin lines that were wrapped mid-sentence (no terminal punctuation)
    text = re.sub(r"(?<![.!?:;…\"”’])\n(?!\n)(?=[^\n])", " ", text)
    return normalize(text)


def parse_docx(path: Path) -> Book:
    import docx

    d = docx.Document(str(path))
    lines: list[str] = []
    for p in d.paragraphs:
        t = p.text.strip()
        if not t:
            lines.append("")
            continue
        style = (p.style.name or "").lower() if p.style is not None else ""
        if style.startswith("heading") or style.startswith("title"):
            lines.append("")
            lines.append(t)
            lines.append("")
        else:
            lines.append(t)
    text = normalize("\n".join(lines))
    title = (d.core_properties.title or "").strip() or path.stem
    return Book(title=title, source=str(path), format="docx", chapters=split_by_headings(text, title))


def _convert_with_calibre(path: Path) -> Path:
    exe = shutil.which("ebook-convert") or next(
        (p for p in [Path(r"C:\Program Files\Calibre2\ebook-convert.exe"),
                     Path(r"C:\Program Files (x86)\Calibre2\ebook-convert.exe")] if p.exists()), None)
    if not exe:
        raise ValueError("Định dạng này cần Calibre (ebook-convert) — hãy cài calibre.com hoặc chuyển sang EPUB.")
    out = Path(tempfile.mkdtemp()) / (path.stem + ".epub")
    subprocess.run([str(exe), str(path), str(out)], check=True, capture_output=True)
    return out


SUPPORTED = {".txt", ".md", ".markdown", ".epub", ".pdf", ".docx", ".srt", ".mobi", ".azw", ".azw3", ".fb2"}


def parse_file(path: Path, title: str | None = None) -> Book:
    ext = path.suffix.lower()
    if ext in (".txt", ".md", ".markdown"):
        book = parse_plain(_read_text_file(path), title or path.stem)
        book.source, book.format = str(path), ext.lstrip(".")
    elif ext == ".epub":
        book = parse_epub(path)
    elif ext == ".pdf":
        book = parse_pdf(path)
    elif ext == ".docx":
        book = parse_docx(path)
    elif ext == ".srt":
        book = parse_srt_file(path)
    elif ext in (".mobi", ".azw", ".azw3", ".fb2"):
        book = parse_epub(_convert_with_calibre(path))
        book.source, book.format = str(path), ext.lstrip(".")
    else:
        raise ValueError(f"Định dạng không hỗ trợ: {ext}")
    if title:
        book.title = title
    if not book.chapters:
        raise ValueError("Không tìm thấy nội dung văn bản")
    return book
