"""RAGPipeline：编排完整检索-回答链路。"""
from __future__ import annotations

import json
import time
from dataclasses import asdict

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import get_db
from app.prompts import answer_generator
from app.services import conversations, settings_service
from app.services.llm.client import LLMClient, LLMError
from app.services.rag import steps
from app.services.rag.context_builder import ContextBuilder
from app.services.retrieval.retriever import Retriever

logger = get_logger(__name__)


class RAGError(Exception):
    """RAG 流程错误（可转为友好提示）。"""


class NoDocumentsError(RAGError):
    pass


class Trace:
    def __init__(self) -> None:
        self.steps: list[dict] = []

    def record(self, name: str, data) -> None:
        self.steps.append({"name": name, "data": data, "ts": time.time()})

    def to_dict(self) -> list[dict]:
        return self.steps


class RAGPipeline:
    def __init__(self) -> None:
        self.llm = LLMClient()
        self.retriever = Retriever()
        self.context_builder = ContextBuilder()

    async def answer(self, query: str, conversation_id: str | None = None, mode: str | None = None) -> dict:
        trace = Trace()

        ready = await self._count_ready()
        if ready == 0:
            raise NoDocumentsError("知识库中还没有可用文档，请先在「知识库」页面导入文档。")

        # 1. 问题理解
        plan = await steps.analyze_query(self.llm, query)
        trace.record("query_analyzer", plan)

        # 2. 多轮改写
        standalone = await steps.rewrite_query(self.llm, query, conversation_id)
        trace.record("query_rewriter", {"standalone_query": standalone})

        # 3. 模式选择：显式参数 > 后台默认模式 > 复杂度自动判断
        if mode and mode.lower() in ("fast", "standard", "deep"):
            mode = mode.lower()
        else:
            public_cfg = await settings_service.get_public()
            default_mode = public_cfg.get("default_chat_mode") or "auto"
            if default_mode == "auto":
                mode = (plan.get("complexity") or "standard").lower()
            else:
                mode = default_mode
        if mode not in ("fast", "standard", "deep"):
            mode = "standard"

        # 4. 候选召回（deep 模式先做 Query Expansion）
        retrieval_plan = {**plan, "standalone_query": standalone}
        if mode == "deep":
            expansions = await steps.expand_query(self.llm, standalone)
            if expansions:
                retrieval_plan["keywords"] = list(retrieval_plan.get("keywords") or []) + expansions
                trace.record("query_expansion", {"queries": expansions})

        retrieval = await self.retriever.retrieve(retrieval_plan)
        trace.record(
            "retrieval",
            {
                "candidate_documents": [
                    {
                        "document_id": c.document_id,
                        "title": c.title,
                        "score": round(c.score, 2),
                        "reasons": c.reasons,
                    }
                    for c in retrieval.candidates[:10]
                ],
                "candidate_sections": [
                    {
                        "section_id": s.section_id,
                        "document_id": s.document_id,
                        "heading": s.heading,
                        "score": round(s.score, 2),
                        "reason": s.reason,
                    }
                    for s in retrieval.sections[:15]
                ],
            },
        )

        # 没有任何候选资料时直接进入“知识不足”，避免继续调用文档选择、
        # 答案生成和可回答性判断，让无依据问题更快、更稳定地闭环。
        if not retrieval.candidates:
            reason = "未检索到与问题相关的可用知识库内容"
            trace.record(
                "answerability",
                {"answer_status": "insufficient_knowledge", "reason": reason},
            )
            return {
                "answer": steps.INSUFFICIENT_ANSWER,
                "citations": [],
                "mode": mode,
                "trace": trace.to_dict(),
                "token_usage": self.llm.collect_usage(),
                "validation": None,
                "answer_status": "insufficient_knowledge",
                "insufficient_reason": reason,
                "retrieval": {
                    "candidate_documents": [],
                    "candidate_sections": [],
                    "context_chars": 0,
                },
            }

        # 5. 文档选择 + 上下文构建
        if mode == "fast":
            top_docs = retrieval.candidates[:3]
            selected_docs = await self._load_doc_infos([c.document_id for c in top_docs])
            doc_ids = {d["document_id"] for d in selected_docs}
            sections = [s for s in retrieval.sections if s.document_id in doc_ids][:6]
            context = await self.context_builder.build(
                selected_docs, [asdict(s) for s in sections], expand_neighbors=False
            )
        else:
            candidates = [
                {"document_id": c.document_id, "title": c.title, "score": c.score, "reasons": c.reasons}
                for c in retrieval.candidates
            ]
            selected = await steps.select_documents(self.llm, standalone, candidates)
            trace.record("document_selector", selected)
            selected_docs = await self._load_doc_infos([s["document_id"] for s in selected])
            selected_ids = {d["document_id"] for d in selected_docs}
            sections = [s for s in retrieval.sections if s.document_id in selected_ids]

            if mode == "deep":
                titles = {d["document_id"]: d.get("title", "") for d in selected_docs}
                reranked = await steps.rerank_sections(
                    self.llm, standalone, [asdict(s) for s in sections], titles
                )
                trace.record(
                    "reranker",
                    [
                        {
                            "section_id": r["section_id"],
                            "heading": r.get("heading"),
                            "relevance": r.get("relevance"),
                            "reason": r.get("reason"),
                        }
                        for r in reranked[:15]
                    ],
                )
                top_sections = reranked[: settings.top_sections_after_rerank]
                context = await self.context_builder.build(
                    selected_docs, top_sections, expand_neighbors=True
                )
            else:
                context = await self.context_builder.build(
                    selected_docs, [asdict(s) for s in sections], expand_neighbors=True
                )

        trace.record(
            "context",
            {
                "used_chars": context.used_chars,
                "truncated": context.truncated,
                "citations": [asdict(c) for c in context.citations],
            },
        )

        # 6. 答案生成
        system, user = answer_generator.build(standalone, context.text or "（知识库中未检索到相关内容）")
        answer = await self.llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            call_type="answer",
        )
        trace.record("answer", {"chars": len(answer)})

        # 7. 证据校验（deep 模式）
        validation = None
        if mode == "deep" and context.text:
            validation = await steps.validate_answer(self.llm, standalone, context.text, answer)
            if not validation.get("supported") and validation.get("corrected_answer"):
                answer = validation["corrected_answer"]
            trace.record("evidence_validator", validation)

        # 8. 可回答性判断（Answer Status）
        judge = await steps.judge_answerability(self.llm, standalone, context.text, answer)
        answer_status = "answered"
        insufficient_reason = None
        if not judge.get("answerable"):
            answer_status = "insufficient_knowledge"
            insufficient_reason = judge.get("reason") or ""
            answer = steps.INSUFFICIENT_ANSWER
        trace.record("answerability", {"answer_status": answer_status, **judge})

        usage = self.llm.collect_usage()
        return {
            "answer": answer,
            "citations": [asdict(c) for c in context.citations],
            "mode": mode,
            "trace": trace.to_dict(),
            "token_usage": usage,
            "validation": validation,
            "answer_status": answer_status,
            "insufficient_reason": insufficient_reason,
            "retrieval": {
                "candidate_documents": [
                    {"document_id": c.document_id, "title": c.title, "score": round(c.score, 2), "reasons": c.reasons}
                    for c in retrieval.candidates[:10]
                ],
                "candidate_sections": [
                    {"section_id": s.section_id, "heading": s.heading, "score": round(s.score, 2), "reason": s.reason}
                    for s in retrieval.sections[:15]
                ],
                "context_chars": context.used_chars,
            },
        }

    async def stream_answer(
        self, query: str, conversation_id: str | None = None, mode: str | None = None
    ):
        """流式回答。yield 事件 dict。"""
        trace = Trace()
        try:
            ready = await self._count_ready()
            if ready == 0:
                yield {"type": "error", "message": "知识库中还没有可用文档，请先在「知识库」页面导入文档。"}
                return

            plan = await steps.analyze_query(self.llm, query)
            trace.record("query_analyzer", plan)
            yield {"type": "stage", "stage": "analyze", "label": "正在理解问题…"}
            standalone = await steps.rewrite_query(self.llm, query, conversation_id)
            trace.record("query_rewriter", {"standalone_query": standalone})
            if mode and mode.lower() in ("fast", "standard", "deep"):
                mode = mode.lower()
            else:
                public_cfg = await settings_service.get_public()
                default_mode = public_cfg.get("default_chat_mode") or "auto"
                if default_mode == "auto":
                    mode = (plan.get("complexity") or "standard").lower()
                else:
                    mode = default_mode
            if mode not in ("fast", "standard", "deep"):
                mode = "standard"

            retrieval_plan = {**plan, "standalone_query": standalone}
            if mode == "deep":
                expansions = await steps.expand_query(self.llm, standalone)
                if expansions:
                    retrieval_plan["keywords"] = list(retrieval_plan.get("keywords") or []) + expansions
                    trace.record("query_expansion", {"queries": expansions})
            yield {"type": "stage", "stage": "retrieve", "label": "正在检索知识库…"}
            retrieval = await self.retriever.retrieve(retrieval_plan)
            trace.record(
                "retrieval",
                {
                    "candidate_documents": [
                        {
                            "document_id": c.document_id,
                            "title": c.title,
                            "score": round(c.score, 2),
                            "reasons": c.reasons,
                        }
                        for c in retrieval.candidates[:10]
                    ],
                    "candidate_sections": [
                        {
                            "section_id": s.section_id,
                            "document_id": s.document_id,
                            "heading": s.heading,
                            "score": round(s.score, 2),
                            "reason": s.reason,
                        }
                        for s in retrieval.sections[:15]
                    ],
                },
            )

            if not retrieval.candidates:
                reason = "未检索到与问题相关的可用知识库内容"
                trace.record(
                    "answerability",
                    {"answer_status": "insufficient_knowledge", "reason": reason},
                )
                yield {
                    "type": "done",
                    "answer": steps.INSUFFICIENT_ANSWER,
                    "citations": [],
                    "mode": mode,
                    "validation": None,
                    "token_usage": self.llm.collect_usage(),
                    "trace": trace.to_dict(),
                    "answer_status": "insufficient_knowledge",
                    "insufficient_reason": reason,
                    "retrieval": {
                        "candidate_documents": [],
                        "candidate_sections": [],
                        "context_chars": 0,
                    },
                }
                return

            yield {"type": "stage", "stage": "select", "label": "正在筛选相关文档…"}
            if mode == "fast":
                top_docs = retrieval.candidates[:3]
                selected_docs = await self._load_doc_infos([c.document_id for c in top_docs])
                doc_ids = {d["document_id"] for d in selected_docs}
                sections = [s for s in retrieval.sections if s.document_id in doc_ids][:6]
                context = await self.context_builder.build(
                    selected_docs, [asdict(s) for s in sections], expand_neighbors=False
                )
            else:
                candidates = [
                    {"document_id": c.document_id, "title": c.title, "score": c.score, "reasons": c.reasons}
                    for c in retrieval.candidates
                ]
                selected = await steps.select_documents(self.llm, standalone, candidates)
                trace.record("document_selector", selected)
                selected_docs = await self._load_doc_infos([s["document_id"] for s in selected])
                selected_ids = {d["document_id"] for d in selected_docs}
                sections = [s for s in retrieval.sections if s.document_id in selected_ids]

                if mode == "deep":
                    titles = {d["document_id"]: d.get("title", "") for d in selected_docs}
                    reranked = await steps.rerank_sections(
                        self.llm, standalone, [asdict(s) for s in sections], titles
                    )
                    trace.record(
                        "reranker",
                        [
                            {
                                "section_id": r["section_id"],
                                "heading": r.get("heading"),
                                "relevance": r.get("relevance"),
                                "reason": r.get("reason"),
                            }
                            for r in reranked[:15]
                        ],
                    )
                    top_sections = reranked[: settings.top_sections_after_rerank]
                    context = await self.context_builder.build(
                        selected_docs, top_sections, expand_neighbors=True
                    )
                else:
                    context = await self.context_builder.build(
                        selected_docs, [asdict(s) for s in sections], expand_neighbors=True
                    )

            trace.record(
                "context",
                {
                    "used_chars": context.used_chars,
                    "truncated": context.truncated,
                    "citations": [asdict(c) for c in context.citations],
                },
            )

            yield {
                "type": "meta",
                "mode": mode,
                "conversation_id": conversation_id,
            }

            # 流式答案生成
            yield {"type": "stage", "stage": "answer", "label": "正在生成回答…"}
            system, user = answer_generator.build(standalone, context.text or "（知识库中未检索到相关内容）")
            chunks: list[str] = []
            async for delta in self.llm.stream_chat(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                call_type="answer",
            ):
                chunks.append(delta)
                yield {"type": "delta", "text": delta}
            answer = "".join(chunks)
            trace.record("answer", {"chars": len(answer)})

            validation = None
            if mode == "deep" and context.text:
                validation = await steps.validate_answer(self.llm, standalone, context.text, answer)
                if not validation.get("supported") and validation.get("corrected_answer"):
                    answer = validation["corrected_answer"]
                trace.record("evidence_validator", validation)

            # 可回答性判断（Answer Status）
            yield {"type": "stage", "stage": "verify", "label": "正在校验回答依据…"}
            judge = await steps.judge_answerability(self.llm, standalone, context.text, answer)
            answer_status = "answered"
            insufficient_reason = None
            if not judge.get("answerable"):
                answer_status = "insufficient_knowledge"
                insufficient_reason = judge.get("reason") or ""
                answer = steps.INSUFFICIENT_ANSWER
            trace.record("answerability", {"answer_status": answer_status, **judge})

            usage = self.llm.collect_usage()
            yield {
                "type": "done",
                "answer": answer,
                "citations": [asdict(c) for c in context.citations],
                "mode": mode,
                "validation": validation,
                "token_usage": usage,
                "trace": trace.to_dict(),
                "answer_status": answer_status,
                "insufficient_reason": insufficient_reason,
                "retrieval": {
                    "candidate_documents": [
                        {"document_id": c.document_id, "title": c.title, "score": round(c.score, 2), "reasons": c.reasons}
                        for c in retrieval.candidates[:10]
                    ],
                    "candidate_sections": [
                        {"section_id": s.section_id, "heading": s.heading, "score": round(s.score, 2), "reason": s.reason}
                        for s in retrieval.sections[:15]
                    ],
                    "context_chars": context.used_chars,
                },
            }
        except Exception as exc:
            logger.exception("RAG 流式处理失败")
            # 与 chat.py 非流式路径保持一致：LLM 异常 → model_error，其余（检索/上下文等）→ retrieval_error
            answer_status = "model_error" if isinstance(exc, LLMError) else "retrieval_error"
            yield {
                "type": "error",
                "message": _friendly_error(exc),
                "answer_status": answer_status,
            }

    # ---------- 工具 ----------

    async def _count_ready(self) -> int:
        db = get_db()
        row = await db.execute_fetchone("SELECT COUNT(*) AS c FROM documents WHERE status='ready'")
        return row["c"] if row else 0

    async def _load_doc_infos(self, doc_ids: list[str]) -> list[dict]:
        if not doc_ids:
            return []
        db = get_db()
        result = []
        for doc_id in doc_ids:
            row = await db.execute_fetchone(
                "SELECT id, title, full_text, char_count, metadata FROM documents WHERE id=? AND status='ready'",
                (doc_id,),
            )
            if row is not None:
                meta = None
                if row["metadata"]:
                    try:
                        meta = json.loads(row["metadata"])
                    except json.JSONDecodeError:
                        meta = None
                result.append(
                    {
                        "document_id": row["id"],
                        "title": row["title"] or "",
                        "full_text": row["full_text"] or "",
                        "char_count": row["char_count"] or 0,
                        "metadata": meta,
                    }
                )
        return result


def _friendly_error(exc: Exception) -> str:
    from app.services.llm.client import LLMNotConfiguredError, LLMTimeoutError

    if isinstance(exc, LLMNotConfiguredError):
        return "尚未配置 LLM。请前往「设置」填写 Base URL / API Key / Model 后再试。"
    if isinstance(exc, LLMTimeoutError):
        return "LLM 请求超时，请稍后重试或增大超时时间。"
    if isinstance(exc, NoDocumentsError):
        return str(exc)
    return f"处理失败：{exc}"
