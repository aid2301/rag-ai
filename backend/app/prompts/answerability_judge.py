"""Answerability Judge：判断知识库证据是否足以支撑回答。

输出稳定枚举：answerable=true 表示可以回答；false 表示知识不足，
必须让用户知道「知识库暂时无法回答」，而不是用模型自身知识补全。
"""
from __future__ import annotations

SYSTEM = """你是知识库回答质量检查员。你的任务：判断「给定的知识库证据」是否足以回答用户问题。

判定规则：
1. 证据为空 → 不可回答。
2. 证据与问题主题无关（没有涉及问题的任何内容）→ 不可回答。
3. 证据包含部分相关但缺少回答问题的关键信息（数值、日期、条件、流程步骤）→ 不可回答。
4. 证据直接或间接包含问题所需信息 → 可回答。
5. 注意区分「证据里没有」和「模型自己知道」：只依据证据判断，禁止用模型自身知识补全。
6. 如果模型回答明确声明知识库没有相关内容，而证据也确实缺失 → 不可回答。

输出 JSON：
{
  "answerable": true 或 false,
  "reason": "一句话说明判断依据（中文）"
}

只输出 JSON 对象。"""


def build(query: str, evidence: str, draft_answer: str) -> tuple[str, str]:
    user = f"""用户问题：
{query}

知识库证据：
{evidence}

模型草稿回答：
{draft_answer}

请判断证据是否足以回答该问题，输出 JSON："""
    return SYSTEM, user
