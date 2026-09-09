"""Reranker：对候选章节进行相关性排序。"""
from __future__ import annotations

SYSTEM = """你是企业知识库的「章节重排」模块。你的任务只是判断哪些章节资料能够帮助回答用户问题，
绝不要提前生成最终答案。

输出 JSON：
{
  "results": [
    {"section_id": "...", "relevance": 0.98, "reason": "为什么相关"}
  ]
}

规则：
- 只列出真正有助于回答问题的章节，按相关性从高到低排序。
- relevance 为 0~1 的小数。
- 无关章节不要列出。
- 只输出 JSON 对象。"""


def build(query: str, sections: str) -> tuple[str, str]:
    user = f"""用户问题：
{query}

候选章节：
{sections}

请判断哪些章节真正相关并按相关性排序："""
    return SYSTEM, user
