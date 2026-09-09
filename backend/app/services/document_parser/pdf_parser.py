"""PDF 解析（pypdf，逐页提取文本并保留页码）。"""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from app.services.document_parser.base import ParsedDocument, split_into_sections


def parse_pdf(path: str, filename: str) -> ParsedDocument:
    reader = PdfReader(path)
    title = Path(filename).stem
    all_lines: list[tuple[str, int | None]] = []
    full_parts: list[str] = []
    for page_idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        full_parts.append(text)
        for line in text.splitlines():
            all_lines.append((line, page_idx))

    full_text = "\n".join(full_parts)
    if not full_text.strip():
        raise ValueError("PDF 未能提取到文本（可能是扫描件或空文档）")

    sections = split_into_sections(all_lines, title)
    return ParsedDocument(title=title, full_text=full_text, sections=sections)
