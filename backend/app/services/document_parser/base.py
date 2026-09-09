"""文档解析统一结构 + 章节切分逻辑。"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.utils.text import detect_heading

# 标题行最大长度（超过则视为正文，降低误判）
_HEADING_LINE_MAX = 60


@dataclass
class ParsedSection:
    heading: str
    content: str
    level: int
    page_number: int | None = None
    parent_heading: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.content)


@dataclass
class ParsedDocument:
    title: str
    full_text: str
    sections: list[ParsedSection] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.full_text)


def split_into_sections(
    lines: list[tuple[str, int | None]],
    default_heading: str,
    max_section_chars: int = 4000,
) -> list[ParsedSection]:
    """把带页码的行序列切分为章节结构。

    lines: [(文本, 页码)]。标题识别见 utils.text.detect_heading。
    """
    sections: list[ParsedSection] = []
    current: dict | None = None
    stack: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        content = "\n".join(current["lines"]).strip()
        # 保留空内容章节：它们代表无正文的父级标题，对结构检索有意义
        sections.append(
            ParsedSection(
                heading=current["heading"],
                content=content,
                level=current["level"],
                page_number=current["page"],
                parent_heading=current["parent"],
            )
        )
        current = None

    for raw_text, page in lines:
        text = raw_text.rstrip()
        if not text.strip():
            continue
        heading = None
        if len(text) <= _HEADING_LINE_MAX:
            heading = detect_heading(text)
        if heading is not None:
            level, heading_text = heading
            flush()
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else None
            stack.append((level, heading_text))
            current = {
                "heading": heading_text,
                "level": level,
                "page": page,
                "parent": parent,
                "lines": [],
            }
        else:
            if current is None:
                current = {
                    "heading": default_heading,
                    "level": 1,
                    "page": page,
                    "parent": None,
                    "lines": [],
                }
                stack = [(1, default_heading)]
            current["lines"].append(text)

    flush()
    return _enforce_limit(sections, max_section_chars)


def _enforce_limit(
    sections: list[ParsedSection], max_chars: int
) -> list[ParsedSection]:
    """超长章节进一步切分（按自然段累计，不超过 max_chars）。"""
    result: list[ParsedSection] = []
    for s in sections:
        if s.char_count <= max_chars:
            result.append(s)
            continue
        parts = _split_long_text(s.content, max_chars)
        for i, part in enumerate(parts):
            suffix = f"（{i + 1}/{len(parts)}）" if len(parts) > 1 else ""
            result.append(
                ParsedSection(
                    heading=s.heading + suffix,
                    content=part,
                    level=s.level,
                    page_number=s.page_number,
                    parent_heading=s.parent_heading,
                )
            )
    return result


def _split_long_text(text: str, max_chars: int) -> list[str]:
    paragraphs = text.split("\n")
    parts: list[str] = []
    buf: list[str] = []
    size = 0
    for para in paragraphs:
        add = len(para) + (1 if buf else 0)
        if buf and size + add > max_chars:
            parts.append("\n".join(buf))
            buf = []
            size = 0
        buf.append(para)
        size += len(para) + (1 if len(buf) > 1 else 0)
    if buf:
        parts.append("\n".join(buf))
    return parts or [text]
