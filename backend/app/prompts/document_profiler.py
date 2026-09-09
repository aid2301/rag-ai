"""Document Profiler：为文档生成画像。"""
from __future__ import annotations

SYSTEM = """你是企业文档分析专家。阅读文档内容，生成一份「文档画像」，帮助后续检索判断文档相关性。

输出 JSON：
{
  "title": "文档标题",
  "summary": "2-3 句话概述文档内容",
  "topics": ["主题列表"],
  "entities": ["实体、岗位、编号、政策名等"],
  "keywords": ["检索关键词，中文优先"],
  "possible_questions": ["用户可能针对本文档提出的 3-8 个问题"]
}

规则：
- 只依据文档内容生成，不要编造。
- 只输出 JSON 对象。"""


def build(title: str, content: str) -> tuple[str, str]:
    user = f"""文档名：{title}

文档内容：
{content}

请生成文档画像 JSON："""
    return SYSTEM, user
