"""Conversation Summarizer：长期对话摘要。"""
from __future__ import annotations

SYSTEM = """你是企业知识库的「对话摘要」模块。根据已有摘要和最近的对话内容，生成/更新一段
长期对话摘要，用于多轮问答的上下文。

要求：
- 保留关键话题、用户关注点、已问过的问题、已给出的关键结论
- 控制在 200 字以内
- 只输出摘要文本，不要任何前缀或解释"""


def build(old_summary: str, recent: str) -> tuple[str, str]:
    user = f"""已有摘要：
{old_summary or "（无）"}

最近对话：
{recent}

请输出更新后的摘要："""
    return SYSTEM, user
