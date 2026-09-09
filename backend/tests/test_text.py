# All document content and business values in this file are fictional test fixtures.
"""中文 tokenizer 与标题识别测试。"""
from __future__ import annotations

from app.utils.text import (
    build_match_query,
    detect_heading,
    tokenize_for_fts,
    tokens_for_query,
)


def test_tokenize_cjk_bigram():
    assert tokenize_for_fts("时长") == "时长"
    assert tokenize_for_fts("项目") == "项目"
    # 三个字 -> 两个重叠双字组
    assert tokenize_for_fts("星桥项目") == "星桥 桥项 项目"
    # 单字保留
    assert tokenize_for_fts("我") == "我"


def test_tokenize_ascii_preserved():
    assert tokenize_for_fts("DEMO2048") == "DEMO2048"
    # 百分比中的数字被保留，% 作为分隔符丢弃
    assert tokenize_for_fts("10%-15%") == "10 15"


def test_tokenize_mixed():
    out = tokenize_for_fts("星桥项目时长 30 分钟")
    # 星桥项目时长 -> 星桥 桥项 项目 目时 时长
    assert "星桥" in out and "时长" in out and "30" in out


def test_build_match_query():
    q = build_match_query(["星桥项目", "时长"])
    assert '"星桥 桥项 项目"' in q
    assert '"时长"' in q
    assert " OR " in q


def test_build_match_query_dedup_and_empty():
    assert build_match_query([]) == ""
    assert build_match_query(["", "  "]) == ""
    q = build_match_query(["时长", "时长"])
    assert q.count("时长") == 1


def test_detect_heading_markdown():
    assert detect_heading("# 标题") == (1, "标题")
    assert detect_heading("## 二级标题") == (2, "二级标题")
    assert detect_heading("### 三级") == (3, "三级")


def test_detect_heading_numbered():
    assert detect_heading("1. 活动日程") == (1, "活动日程")
    assert detect_heading("1.1 开始时间") == (2, "开始时间")
    assert detect_heading("1.1.1 细则") == (3, "细则")
    assert detect_heading("一、项目范围") == (1, "项目范围")
    assert detect_heading("（1）某条款") == (1, "某条款")


def test_detect_heading_list_item_not_heading():
    # 以句末标点结尾的编号行是列表正文，不是标题
    assert detect_heading("1. 星桥项目默认时长为 30 分钟。") is None
    assert detect_heading("2. 每场演示 2 小时。") is None


def test_detect_heading_none():
    assert detect_heading("这是一段普通正文") is None
    assert detect_heading("") is None
