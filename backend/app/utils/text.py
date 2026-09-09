"""文本处理工具。

核心是 `tokenize_for_fts`：SQLite FTS5 默认 unicode61 tokenizer 无法切分中文，
trigram 又无法匹配 2 字词。这里采用「中文双字组（bigram）索引」方案：

- 连续中文片段 -> 重叠双字组（单字保留原样）
- ASCII 字母数字片段（编号、金额、百分比）-> 整体保留
- 其他标点/空白 -> 作为分隔符丢弃

索引与查询使用同一套 tokenize，从而让「时长 / 项目 / 星桥项目 / DEMO2048」等
短词都能可靠命中。
"""
from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_HEADING_PATTERNS = [
    re.compile(r"^\s*(#{1,6})\s+(.+)$"),                                  # Markdown
    re.compile(r"^\s*(\d+(?:\.\d+){0,4})\s*[、.．:：\s]\s*(.+)$"),           # 1. / 1.1 / 1.1.1
    re.compile(r"^\s*[（(]\s*(\d+(?:\.\d+){0,4})\s*[)）]\s*[、.．:：]?\s*(.+)$"),  # （1）/(1)
    re.compile(r"^\s*([一二三四五六七八九十]+)\s*[、.．:：]\s*(.+)$"),            # 一、
    re.compile(r"^\s*第\s*([一二三四五六七八九十0-9]+)\s*[章节部分条]\s*(.+)$"),   # 第X章
]


def is_cjk(ch: str) -> bool:
    return bool(_CJK_RE.match(ch))


def tokenize_for_fts(text: str) -> str:
    """把文本转换为 FTS5 可检索的 token 串（空格分隔）。"""
    if not text:
        return ""
    tokens: list[str] = []
    cur: list[str] = []
    mode: str | None = None  # None / 'cjk' / 'ascii'

    def flush() -> None:
        nonlocal cur, mode
        if not cur:
            return
        seg = "".join(cur)
        if mode == "cjk":
            if len(seg) == 1:
                tokens.append(seg)
            else:
                tokens.extend(seg[i : i + 2] for i in range(len(seg) - 1))
        else:
            tokens.append(seg)
        cur = []
        mode = None

    for ch in text:
        if is_cjk(ch):
            if mode != "cjk":
                flush()
                mode = "cjk"
            cur.append(ch)
        elif ch.isalnum() and ord(ch) < 128:
            if mode != "ascii":
                flush()
                mode = "ascii"
            cur.append(ch)
        else:
            flush()
    flush()
    return " ".join(tokens)


def tokens_for_query(text: str) -> str:
    """查询侧 token 串，与索引侧保持一致。"""
    return tokenize_for_fts(text)


def build_match_query(keywords: list[str]) -> str:
    """把关键词列表拼成 FTS5 MATCH 表达式。

    每个关键词的 bigram 作为 phrase，多个关键词之间 OR 连接，
    由 BM25 对命中更多关键词的文档加权。
    """
    phrases: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        if not kw or not kw.strip():
            continue
        toks = tokenize_for_fts(kw.strip())
        if not toks:
            continue
        phrase = '"' + toks + '"'
        if phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)
    if not phrases:
        return ""
    return " OR ".join(phrases)


def char_count(text: str) -> int:
    return len(text)


def detect_heading(line: str) -> tuple[int, str] | None:
    """识别一行文本是否为标题，返回 (层级, 标题文本) 或 None。"""
    line = line.rstrip()
    for idx, pat in enumerate(_HEADING_PATTERNS):
        m = pat.match(line)
        if m:
            if idx == 0:  # Markdown 标题：显式标记，始终视为标题
                return len(m.group(1)), m.group(2).strip()
            # 数字/中文数字标题：以句末标点结尾的通常是列表项正文，而非标题
            if line[-1:] in "。！？；…":
                continue
            text = m.group(2).strip()
            if len(text) > 40:
                continue
            num = m.group(1).replace("（", "").replace("(", "")
            if num and num[0].isdigit():
                level = min(num.count(".") + 1, 6)
            else:
                level = 1
            return level, text
    return None


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"
