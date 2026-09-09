"""Section Summarizer：为章节生成精简摘要。"""
from __future__ import annotations

SYSTEM = """你是文档摘要助手。为给定章节生成一句精简摘要，概括其核心内容。

只输出这一句摘要，不要任何前缀或解释。"""


def build(heading: str, content: str) -> tuple[str, str]:
    user = f"""章节标题：{heading or "（无标题）"}

章节内容：
{content}

一句话摘要："""
    return SYSTEM, user
