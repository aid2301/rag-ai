"""Query Rewriter：结合对话历史把问题改写为独立可检索的表述。"""
from __future__ import annotations

SYSTEM = """你是企业知识库的「多轮对话改写」模块。结合对话历史，把用户当前问题改写成一个
完整、独立、不含指代（如"他/那/这个"）的问题，使其脱离历史也能被单独理解和检索。

如果当前问题本身已经完整，直接原样返回。
如果当前问题依赖历史（如"那男团呢？"），必须结合历史补全上下文。

只输出改写后的单个问题文本，不要任何解释或 JSON。"""


def build(conversation_summary: str, recent_history: str, query: str) -> tuple[str, str]:
    user = f"""对话长期摘要：
{conversation_summary or "（无）"}

最近几轮对话：
{recent_history or "（无）"}

当前用户问题：
{query}

请输出改写后的独立问题："""
    return SYSTEM, user
