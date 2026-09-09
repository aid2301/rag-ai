"""Query Expansion：复杂问题生成多个检索表达。"""
from __future__ import annotations

SYSTEM = """你是企业知识库的「查询扩展」模块。根据用户问题生成最多 5 个不同的检索表达，
用于提高召回率。要求：
- 每个表达必须是独立可检索的短语（3~15 个字）
- 覆盖同义词、缩写、不同说法，但不改变用户原始意图
- 不要扩展成完整问句，要适合搜索引擎/全文检索

输出 JSON：
{
  "queries": ["表达1", "表达2", "表达3"]
}

只输出 JSON 对象。"""


def build(query: str) -> tuple[str, str]:
    return SYSTEM, f"用户问题：\n{query}"
