"""RAG 各 LLM 步骤（均带 LLM 不可用时的降级回退）。"""
from __future__ import annotations

import json

from app.core.logging import get_logger
from app.db.database import get_db
from app.prompts import (
    answerability_judge,
    conversation_summarizer,
    document_selector,
    evidence_validator,
    query_analyzer,
    query_expansion,
    query_rewriter,
    reranker,
)
from app.services import conversations, settings_service
from app.services.llm.client import LLMClient, LLMError, LLMNotConfiguredError

logger = get_logger(__name__)

_ANALYZER_HINT = (
    "请输出 JSON：{standalone_query, intent, entities, keywords, constraints, "
    "needs_comparison, needs_multi_document, complexity}"
)


async def llm_configured() -> bool:
    return (await settings_service.get_llm_config()).configured


async def analyze_query(llm: LLMClient, query: str) -> dict:
    """问题理解。"""
    fallback = {
        "standalone_query": query,
        "intent": "事实查询",
        "entities": [],
        "keywords": [query],
        "constraints": {},
        "needs_comparison": False,
        "needs_multi_document": False,
        "complexity": "standard",
    }
    try:
        system, user = query_analyzer.build(query)
        plan = await llm.structured_object(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            call_type="query_analyzer",
            schema_hint=_ANALYZER_HINT,
        )
        for key, default in fallback.items():
            plan.setdefault(key, default)
        if not plan.get("standalone_query"):
            plan["standalone_query"] = query
        if plan.get("complexity") not in ("fast", "standard", "deep"):
            plan["complexity"] = "standard"
        return plan
    except (LLMError, ValueError) as exc:
        logger.warning("query_analyzer 降级: %s", exc)
        return fallback


async def rewrite_query(
    llm: LLMClient, query: str, conversation_id: str | None
) -> str:
    """多轮对话改写。"""
    if not conversation_id:
        return query
    summary = await conversations.get_summary(conversation_id)
    recent = await conversations.get_recent_messages(conversation_id, limit=6)
    history = "\n".join(
        f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:300]}"
        for m in recent
    )
    try:
        system, user = query_rewriter.build(summary, history, query)
        rewritten = await llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            call_type="query_rewriter",
            temperature=0.0,
            max_tokens=200,
        )
        rewritten = rewritten.strip()
        return rewritten if rewritten else query
    except (LLMError, ValueError) as exc:
        logger.warning("query_rewriter 降级: %s", exc)
        return query


async def expand_query(llm: LLMClient, query: str) -> list[str]:
    """Query Expansion（deep 模式）。"""
    try:
        system, user = query_expansion.build(query)
        data = await llm.structured_object(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            call_type="query_expansion",
            schema_hint='{"queries": ["..."]}',
        )
        queries = [q for q in (data.get("queries") or []) if q and isinstance(q, str)]
        if queries:
            return queries[:5]
    except (LLMError, ValueError) as exc:
        logger.warning("query_expansion 降级: %s", exc)
    return []


async def select_documents(
    llm: LLMClient, query: str, candidates: list[dict]
) -> list[dict]:
    """LLM 文档选择。candidates 为包含 document_id/title/score/reasons 的列表。"""
    if not candidates:
        return []
    try:
        profiles = await _load_profiles([c["document_id"] for c in candidates])
        profile_text = "\n\n".join(
            f"[DOC {i + 1}] id={p['document_id']}\n"
            f"标题: {p['title']}\n摘要: {p['summary']}\n"
            f"主题: {', '.join(p['topics'][:8])}\n实体: {', '.join(p['entities'][:8])}\n"
            f"关键词: {', '.join(p['keywords'][:12])}\n"
            f"可能问题: {', '.join(p['possible_questions'][:5])}"
            for i, p in enumerate(profiles)
        )
        system, user = document_selector.build(query, profile_text)
        data = await llm.structured_object(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            call_type="document_selector",
            schema_hint='{"selected_documents": [{"document_id": "...", "reason": "...", "confidence": 0.9}]}',
        )
        selected = []
        valid_ids = {c["document_id"] for c in candidates}
        for item in data.get("selected_documents") or []:
            doc_id = item.get("document_id")
            if doc_id in valid_ids:
                selected.append(
                    {
                        "document_id": doc_id,
                        "reason": item.get("reason", ""),
                        "confidence": float(item.get("confidence", 0)),
                    }
                )
        if selected:
            return selected
        # 模型没选到任何文档：降级取分数最高的 3 个
        return [
            {"document_id": c["document_id"], "reason": "降级：召回得分最高", "confidence": 0.5}
            for c in candidates[:3]
        ]
    except (LLMError, ValueError) as exc:
        logger.warning("document_selector 降级: %s", exc)
        return [
            {"document_id": c["document_id"], "reason": "降级：召回得分最高", "confidence": 0.5}
            for c in candidates[:3]
        ]


async def rerank_sections(
    llm: LLMClient, query: str, sections: list[dict], doc_titles: dict[str, str]
) -> list[dict]:
    """LLM 章节重排。sections 含 section_id/heading/content/page_number。"""
    if not sections:
        return []
    try:
        body = "\n\n".join(
            f"[SECTION {i + 1}] id={s['section_id']}\n"
            f"文档: {doc_titles.get(s['document_id'], '')}\n"
            f"章节: {s['heading']}\n内容: {s['content'][:600]}"
            for i, s in enumerate(sections)
        )
        system, user = reranker.build(query, body)
        data = await llm.structured_object(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            call_type="reranker",
            schema_hint='{"results": [{"section_id": "...", "relevance": 0.9, "reason": "..."}]}',
        )
        by_id = {s["section_id"]: s for s in sections}
        results = []
        for item in data.get("results") or []:
            sid = item.get("section_id")
            if sid in by_id:
                results.append(
                    {
                        **by_id[sid],
                        "relevance": float(item.get("relevance", 0)),
                        "reason": item.get("reason", ""),
                    }
                )
        results.sort(key=lambda r: r["relevance"], reverse=True)
        return results
    except (LLMError, ValueError) as exc:
        logger.warning("reranker 降级: %s", exc)
        return [dict(s) for s in sections]


async def validate_answer(
    llm: LLMClient, query: str, context: str, draft_answer: str
) -> dict:
    """证据校验。"""
    try:
        system, user = evidence_validator.build(query, context, draft_answer)
        data = await llm.structured_object(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            call_type="evidence_validator",
            schema_hint='{"supported": true, "problems": [], "corrected_answer": null}',
            max_tokens=1500,
        )
        return {
            "supported": bool(data.get("supported", True)),
            "problems": data.get("problems") or [],
            "corrected_answer": data.get("corrected_answer"),
        }
    except (LLMError, ValueError) as exc:
        logger.warning("evidence_validator 降级: %s", exc)
        return {"supported": True, "problems": [], "corrected_answer": None}



INSUFFICIENT_ANSWER = "当前知识库暂时没有找到足够的信息回答这个问题。"


async def judge_answerability(
    llm: LLMClient, query: str, context_text: str, draft_answer: str
) -> dict:
    """判断知识库证据是否足以回答。返回 {answerable, reason, method}。

    method: 'empty'（无证据，直接判定）/ 'llm'（LLM 判定）/ 'fallback'（LLM 不可用降级）
    降级规则：上下文为空 → 不可回答；否则视为可回答（保守，避免误伤）。
    """
    if not (context_text or "").strip():
        return {"answerable": False, "reason": "未检索到任何知识库内容", "method": "empty"}
    try:
        system, user = answerability_judge.build(query, context_text[:12000], draft_answer[:3000])
        data = await llm.structured_object(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            call_type="answerability_judge",
            schema_hint='{"answerable": true, "reason": "..."}',
            temperature=0.0,
            max_tokens=300,
        )
        return {
            "answerable": bool(data.get("answerable", True)),
            "reason": str(data.get("reason") or ""),
            "method": "llm",
        }
    except (LLMError, ValueError) as exc:
        logger.warning("answerability_judge 降级: %s", exc)
        return {"answerable": True, "reason": "判定器不可用，默认可回答", "method": "fallback"}


async def maybe_summarize_conversation(llm: LLMClient, conv_id: str) -> None:
    """消息较多时更新长期摘要。"""
    try:
        msgs = await conversations.get_messages(conv_id, limit=1000)
        if len(msgs) < 10:
            return
        old = await conversations.get_summary(conv_id)
        recent = "\n".join(
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:200]}"
            for m in msgs[-8:]
        )
        system, user = conversation_summarizer.build(old, recent)
        summary = await llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            call_type="conversation_summarizer",
            temperature=0.0,
            max_tokens=300,
        )
        await conversations.set_summary(conv_id, summary.strip())
    except (LLMError, ValueError) as exc:
        logger.warning("对话摘要更新失败: %s", exc)


async def _load_profiles(doc_ids: list[str]) -> list[dict]:
    if not doc_ids:
        return []
    db = get_db()
    profiles = []
    for doc_id in doc_ids:
        row = await db.execute_fetchone(
            "SELECT document_id, title, summary, topics, entities, keywords, possible_questions "
            "FROM document_profiles WHERE document_id=?",
            (doc_id,),
        )
        if row is None:
            continue
        profiles.append(
            {
                "document_id": row["document_id"],
                "title": row["title"] or "",
                "summary": row["summary"] or "",
                "topics": _json_list(row["topics"]),
                "entities": _json_list(row["entities"]),
                "keywords": _json_list(row["keywords"]),
                "possible_questions": _json_list(row["possible_questions"]),
            }
        )
    return profiles


def _json_list(raw) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(x) for x in data] if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []