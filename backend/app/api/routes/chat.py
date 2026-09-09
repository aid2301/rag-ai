"""Chat API：普通回答 + SSE 流式。"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.core.config import settings
from app.core.logging import get_logger
from app.core.user_auth import get_current_user
from app.schemas.api import ChatRequest, ChatResponse, CitationOut
from app.services import conversations
from app.services.llm.client import LLMError
from app.services.rag import steps
from app.services.rag.pipeline import RAGPipeline, RAGError, _friendly_error

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _usage_summary(usage: list[dict]) -> dict:
    summary: dict[str, dict] = {}
    for u in usage:
        ct = u.get("call_type", "other")
        entry = summary.setdefault(
            ct,
            {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "latency_ms": 0},
        )
        entry["calls"] += 1
        entry["prompt_tokens"] += u.get("prompt_tokens", 0)
        entry["completion_tokens"] += u.get("completion_tokens", 0)
        entry["total_tokens"] += u.get("total_tokens", 0)
        entry["latency_ms"] += u.get("latency_ms", 0)
    return summary


async def _ensure_conversation(conv_id: str | None, user_id: str) -> str:
    if conv_id:
        conv = await conversations.get_conversation(conv_id)
        if conv is not None and conv.get("user_id") == user_id:
            return conv_id
    return await conversations.create_conversation(user_id=user_id)


async def _save_assistant(
    conv_id: str,
    answer: str,
    citations: list | None = None,
    trace: list | None = None,
    usage: list | None = None,
    validation: dict | None = None,
    answer_status: str = "answered",
    insufficient_reason: str | None = None,
) -> str:
    debug_info = {"trace": trace} if (trace and settings.debug) else None
    token_usage = _usage_summary(usage or [])
    if validation:
        debug_info = debug_info or {}
        debug_info["validation"] = validation
    return await conversations.add_message(
        conv_id,
        "assistant",
        answer,
        citations=citations or [],
        debug_info=debug_info,
        token_usage=token_usage,
        answer_status=answer_status,
        insufficient_reason=insufficient_reason,
    )


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest, user: dict = Depends(get_current_user)):
    conv_id = await _ensure_conversation(body.conversation_id, user["id"])
    await conversations.add_message(conv_id, "user", body.query)
    await conversations.set_title_if_empty(conv_id, body.query[:30])

    pipeline = RAGPipeline()
    try:
        result = await pipeline.answer(body.query, conv_id, body.mode)
    except RAGError as exc:
        msg = str(exc)
        await _save_assistant(conv_id, msg, answer_status="insufficient_knowledge")
        return ChatResponse(answer=msg, error=True, answer_status="insufficient_knowledge")
    except LLMError as exc:
        msg = _friendly_error(exc)
        await _save_assistant(conv_id, msg, answer_status="model_error")
        return ChatResponse(answer=msg, error=True, answer_status="model_error")
    except Exception as exc:
        logger.exception("Chat 处理失败")
        msg = f"处理失败：{exc}"
        await _save_assistant(conv_id, msg, answer_status="retrieval_error")
        return ChatResponse(answer=msg, error=True, answer_status="retrieval_error")

    msg_id = await _save_assistant(
        conv_id,
        result["answer"],
        citations=result["citations"],
        trace=result["trace"],
        usage=result["token_usage"],
        validation=result["validation"],
        answer_status=result.get("answer_status", "answered"),
        insufficient_reason=result.get("insufficient_reason"),
    )
    try:
        await steps.maybe_summarize_conversation(pipeline.llm, conv_id)
    except Exception:
        logger.debug("对话摘要更新跳过")

    debug = result["trace"] if settings.debug else None
    return ChatResponse(
        answer=result["answer"],
        citations=[CitationOut(**c) for c in result["citations"]],
        mode=result["mode"],
        validation=result["validation"],
        token_usage=result["token_usage"],
        debug=debug,
        answer_status=result.get("answer_status", "answered"),
        insufficient_reason=result.get("insufficient_reason"),
        message_id=msg_id,
    )


@router.post("/stream")
async def chat_stream(body: ChatRequest, user: dict = Depends(get_current_user)):
    conv_id = await _ensure_conversation(body.conversation_id, user["id"])
    await conversations.add_message(conv_id, "user", body.query)
    await conversations.set_title_if_empty(conv_id, body.query[:30])
    pipeline = RAGPipeline()

    async def event_gen():
        yield _sse({"type": "meta", "conversation_id": conv_id})
        answer_parts: list[str] = []
        citations: list = []
        usage: list = []
        trace: list = []
        validation: dict | None = None
        final = None
        error_seen = False
        try:
            async for ev in pipeline.stream_answer(body.query, conv_id, body.mode):
                if ev.get("type") == "delta":
                    answer_parts.append(ev.get("text", ""))
                    yield _sse(ev)
                elif ev.get("type") == "meta":
                    # 首帧 meta（含 conversation_id）已由本函数在流开始前发送；
                    # pipeline 内部的 meta 仅补充 mode（最终 done 亦携带），不重复转发
                    continue
                elif ev.get("type") == "done":
                    final = ev
                    citations = ev.get("citations", [])
                    usage = ev.get("token_usage", [])
                    trace = ev.get("trace", [])
                    validation = ev.get("validation")
                    # 不转发 pipeline 的 done（无 message_id）：保存后统一发送带 message_id 的最终 done
                    continue
                elif ev.get("type") == "error":
                    error_seen = True
                    # 优先采用 pipeline 自带的 answer_status（P2-2：检索阶段异常映射 retrieval_error）；
                    # 无文档场景仍按消息特征回退到 insufficient_knowledge
                    status = ev.get("answer_status") or "model_error"
                    msg = ev.get("message", "回答失败")
                    if "知识库中还没有可用文档" in msg:
                        status = "insufficient_knowledge"
                    msg_id = await _save_assistant(conv_id, msg, answer_status=status)
                    # 透传带 message_id 的 error 事件，保证前端「提交给管理员」可用（P1-3）
                    yield _sse(
                        {
                            "type": "error",
                            "message": msg,
                            "answer_status": status,
                            "message_id": msg_id,
                        }
                    )
                    continue
                else:
                    # stage 等其余事件透传
                    yield _sse(ev)
            if final:
                msg_id = await _save_assistant(
                    conv_id,
                    final["answer"],
                    citations=citations,
                    trace=trace,
                    usage=usage,
                    validation=validation,
                    answer_status=final.get("answer_status", "answered"),
                    insufficient_reason=final.get("insufficient_reason"),
                )
                final["message_id"] = msg_id
                yield _sse({"type": "done", **final})
                try:
                    await steps.maybe_summarize_conversation(pipeline.llm, conv_id)
                except Exception:
                    pass
            else:
                partial = "".join(answer_parts).strip()
                # error 场景已保存错误消息，不再追加「回答被中断」消息（P1-1）
                if not error_seen and partial:
                    await _save_assistant(
                        conv_id, partial + chr(10) + chr(10) + "（回答被中断）"
                    )
        except asyncio.CancelledError:
            partial = "".join(answer_parts).strip()
            if partial:
                try:
                    await _save_assistant(
                        conv_id, partial + chr(10) + chr(10) + "（回答被中断）"
                    )
                except Exception:
                    pass
            raise
        except Exception as exc:
            logger.exception("流式回答异常")
            msg = f"处理失败：{exc}"
            msg_id = await _save_assistant(conv_id, msg, answer_status="retrieval_error")
            yield _sse(
                {
                    "type": "error",
                    "message": msg,
                    "answer_status": "retrieval_error",
                    "message_id": msg_id,
                }
            )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"