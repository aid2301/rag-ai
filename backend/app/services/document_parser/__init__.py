"""统一 Document Parser 入口。"""
from __future__ import annotations

from pathlib import Path

from app.services.document_parser.base import ParsedDocument, ParsedSection
from app.services.document_parser.pdf_parser import parse_pdf
from app.services.document_parser.docx_parser import parse_docx
from app.services.document_parser.text_parser import parse_text
from app.services.document_parser.xlsx_parser import parse_xlsx

__all__ = ["ParsedDocument", "ParsedSection", "parse_document"]

_EXT_MAP = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".txt": parse_text,
    ".md": parse_text,
    ".markdown": parse_text,
    ".xlsx": parse_xlsx,
    ".xls": parse_xlsx,
}

SUPPORTED_EXTENSIONS = tuple(sorted(_EXT_MAP.keys()))


def file_type_of(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return ext.lstrip(".") or "unknown"


def parse_document(path: str, filename: str) -> ParsedDocument:
    ext = Path(filename).suffix.lower()
    parser = _EXT_MAP.get(ext)
    if parser is None:
        raise ValueError(f"不支持的文件类型: {ext}")
    return parser(path, filename)
