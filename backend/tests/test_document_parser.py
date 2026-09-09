# All document content and business values in this file are fictional test fixtures.
"""文档解析器测试（Markdown / 文本）。"""
from __future__ import annotations

from pathlib import Path

from app.services.document_parser import parse_document

SAMPLE_MD = """# 演示手册

## 1. 活动日程

### 1.1 开始时间

演示活动采用预约模式。

### 1.2 入场

预约开始前 5 分钟可以入场。

## 2. 演示设置

### 2.1 默认时长

1. 默认时长为 15 分钟。
2. 场次可调整。
"""


def test_markdown_structure(tmp_path: Path):
    p = tmp_path / "演示手册.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")
    parsed = parse_document(str(p), "演示手册.md")

    assert parsed.title == "演示手册"
    # 结构章节：1.活动日程(空)、1.1、1.2、2.演示设置(空)、2.1
    headings = [s.heading for s in parsed.sections]
    assert "1. 活动日程" in headings
    assert "1.1 开始时间" in headings
    assert "1.2 入场" in headings
    assert "2.1 默认时长" in headings

    # 父级标题关系
    s11 = next(s for s in parsed.sections if s.heading == "1.1 开始时间")
    assert s11.parent_heading == "1. 活动日程"
    assert s11.level == 3

    # 列表项没有被误判为标题
    assert all("默认时长为 15 分钟" not in s.heading for s in parsed.sections)


def test_txt_parse(tmp_path: Path):
    p = tmp_path / "说明.txt"
    p.write_text("这是第一行\n这是第二行", encoding="utf-8")
    parsed = parse_document(str(p), "说明.txt")
    assert parsed.title == "说明"
    assert len(parsed.sections) >= 1
    assert parsed.full_text


def test_unsupported_ext(tmp_path: Path):
    import pytest

    p = tmp_path / "x.xyz"
    p.write_text("abc")
    with pytest.raises(ValueError):
        parse_document(str(p), "x.xyz")
