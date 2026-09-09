"""TXT / Markdown 解析。"""
from __future__ import annotations

from pathlib import Path

from app.services.document_parser.base import ParsedDocument, split_into_sections

_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk", "latin-1")


def parse_text(path: str, filename: str) -> ParsedDocument:
    p = Path(path)
    raw = p.read_bytes()
    text = None
    for enc in _ENCODINGS:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")

    title = Path(filename).stem
    lines = text.splitlines()
    # Markdown 第一个 H1 作为标题
    if filename.lower().endswith((".md", ".markdown")):
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break
    parsed_lines = [(line, None) for line in lines]
    sections = split_into_sections(parsed_lines, title)
    return ParsedDocument(title=title, full_text=text, sections=sections)
