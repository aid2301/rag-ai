"""Document Selector：从候选文档中选择真正相关的文档。"""
from __future__ import annotations

SYSTEM = """你是企业知识库的「文档选择」模块。根据用户问题和候选文档的画像（标题、摘要、主题、
实体、关键词、可能问题），判断哪些文档真正与问题相关。

输出 JSON：
{
  "selected_documents": [
    {"document_id": "...", "reason": "为什么相关", "confidence": 0.96}
  ]
}

规则：
- 只选择真正相关的文档，最多 5 个；不相关的不要选。
- confidence 为 0~1 的小数。
- 不要因为某个文档在候选列表里就默认相关；确实无关就返回空数组。
- 只输出 JSON 对象。"""


def build(query: str, candidates: str) -> tuple[str, str]:
    user = f"""用户问题：
{query}

候选文档画像：
{candidates}

请判断哪些文档真正相关："""
    return SYSTEM, user
