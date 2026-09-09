"""Question Group Suggester：为提交的问题建议最匹配的分组。

输入：用户问题 + 现有分组列表。输出：最匹配分组（含置信度与理由）。
规则匹配优先（关键词表），LLM 仅作为增强；LLM 不可用时静默回退。
"""
from __future__ import annotations

SYSTEM = """你是企业知识库的「问题分组」模块。根据用户提交的问题和现有分组列表，
判断该问题最应该归入哪个分组。

输出 JSON：
{
  "group_id": "匹配的分组 id（没有合适的返回 null）",
  "group_name": "匹配的分组名（没有合适的返回 null）",
  "confidence": 0.0~1.0 的置信度小数,
  "reason": "简短理由"
}

规则：
- 只从给定分组列表中选择；确实没有合适的返回 group_id=null。
- confidence < 0.6 时视为不匹配（返回 null）。
- 不要编造分组名，必须来自给定列表。
- 只输出 JSON 对象。"""


def build(question: str, groups: list[dict]) -> tuple[str, str]:
    """groups: [{"id": "...", "name": "..."}]"""
    if not groups:
        return SYSTEM, "没有可用的分组列表，返回 {\"group_id\": null, \"group_name\": null, \"confidence\": 0, \"reason\": \"无分组\"}"
    lines = "\n".join(f'- {g["id"]} | {g["name"]}' for g in groups)
    user = f"""用户提交的问题：
{question}

现有分组：
{lines}

请判断该问题最匹配的分组："""
    return SYSTEM, user
