"""Evidence Validator：答案事实二次校验。"""
from __future__ import annotations

SYSTEM = """你是企业知识库的「事实校验」模块。检查草稿答案是否有事实错误。

检查项：
- 是否存在没有证据支持的内容
- 数字/金额/日期/百分比是否与证据一致
- 是否混入了其他岗位或文档的信息
- 是否遗漏了重要的限制条件或例外
- 是否错误合并了多个文档
- 是否存在幻觉

输出 JSON：
{
  "supported": true,
  "problems": ["问题描述"],
  "corrected_answer": null
}

规则：
- 如果答案正确，supported 为 true，corrected_answer 为 null。
- 如果发现问题，supported 为 false，corrected_answer 给出修正后的完整答案（保留来源标记）。
- 只输出 JSON 对象。"""


def build(query: str, evidence: str, draft_answer: str) -> tuple[str, str]:
    user = f"""用户问题：
{query}

知识库证据：
{evidence}

草稿答案：
{draft_answer}

请校验并输出 JSON："""
    return SYSTEM, user
