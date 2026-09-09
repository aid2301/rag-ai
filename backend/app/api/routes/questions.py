"""问题库 API：
- POST /api/questions            用户/管理员提交问题（幂等 + 相似合并）
- GET  /api/questions/by-message/{id}  用户查询某消息是否已提交
- GET / PATCH / DELETE /api/questions/{id}   管理员查看/处理/删除
- /api/question-groups           分组 CRUD（删除分组不删问题）
- /api/admin/overview            侧边栏 Badge 计数
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.admin import require_admin, verify_access_token
from app.core.user_auth import get_current_user, get_optional_user
from app.db.database import get_db
from app.services import questions as qs
from app.services import conversations
from app.services import settings_service

router = APIRouter(prefix="/api/questions", tags=["questions"])
groups_router = APIRouter(prefix="/api/question-groups", tags=["question-groups"], dependencies=[Depends(require_admin)])
overview_router = APIRouter(prefix="/api/admin", tags=["admin-overview"], dependencies=[Depends(require_admin)])


class QuestionSubmitBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    conversation_id: str
    message_id: str
    ai_answer: str | None = None
    # M1：回答有误反馈
    feedback_type: str = "insufficient"  # insufficient | wrong_answer
    feedback_note: str | None = None


class QuestionUpdateBody(BaseModel):
    status: str | None = None
    standard_answer: str | None = None
    group_id: str | None = None
    assignee: str | None = None
    question: str | None = None


class QuestionGroupBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)


def _snapshot_from_trace(debug_info: dict | None) -> dict:
    """从消息 debug_info.trace 提取检索快照（候选文档/章节/上下文）。"""
    if not debug_info:
        return {}
    trace = debug_info.get("trace") or []
    snapshot: dict[str, Any] = {}
    for step in trace:
        name = step.get("name")
        data = step.get("data") or {}
        if name == "retrieval":
            snapshot["candidate_documents"] = data.get("candidate_documents") or []
            snapshot["candidate_sections"] = data.get("candidate_sections") or []
        elif name == "context":
            snapshot["context_chars"] = data.get("used_chars")
            snapshot["citations"] = data.get("citations") or []
        elif name == "answerability":
            snapshot["answerability"] = data
    return snapshot


async def _get_submitter(authorization: str | None = Header(default=None)) -> dict:
    """用户或管理员均可提交问题。返回 {kind, user_id}。"""
    user = await get_optional_user(authorization)
    if user is not None:
        return {"kind": "user", "user_id": user["id"]}
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if verify_access_token(token):
        return {"kind": "admin", "user_id": None}
    raise HTTPException(status_code=401, detail="请先登录")


@router.post("")
async def submit_question(
    body: QuestionSubmitBody,
    submitter: dict = Depends(_get_submitter),
):
    """提交问题到问题库。校验来源消息归属；同一消息重复提交幂等。"""
    # 校验消息存在 + 归属
    msg = await conversations.get_message(body.message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    conv = await conversations.get_conversation(msg["conversation_id"])
    if conv is None or conv["id"] != body.conversation_id:
        raise HTTPException(status_code=400, detail="会话与消息不匹配")
    if submitter["kind"] == "user" and conv.get("user_id") != submitter["user_id"]:
        raise HTTPException(status_code=403, detail="无权提交该会话的问题")

    # 从 assistant 消息 debug trace 提取检索快照；模型名从当前配置读取
    snapshot = _snapshot_from_trace(msg.get("debug_info") or {})
    cfg = await settings_service.get_llm_config()
    model = cfg.model or None
    ai_answer = body.ai_answer or msg.get("content")
    # M1：提交时固化来源会话上下文（前后各 3 条），防删除会话/用户后追溯断裂
    context_snapshot = await qs.build_context_snapshot(
        body.conversation_id, body.message_id
    )
    try:
        result = await qs.submit_question(
            question=body.question,
            user_id=submitter["user_id"],
            conversation_id=body.conversation_id,
            message_id=body.message_id,
            ai_answer=ai_answer,
            answer_status=msg.get("answer_status") or "insufficient_knowledge",
            retrieval_snapshot=snapshot,
            model=model,
            feedback_type=body.feedback_type,
            feedback_note=body.feedback_note,
            context_snapshot=context_snapshot,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.get("/by-message/{message_id}")
async def check_message_submitted(
    message_id: str,
    user: dict = Depends(get_current_user),
):
    """用户端：查询自己的某条消息是否已提交问题库（防重复提交/回显状态）。"""
    msg = await conversations.get_message(message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    conv = await conversations.get_conversation(msg["conversation_id"])
    if conv is None or conv.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="消息不存在")
    return await qs.check_submitted(message_id)


# ---------- 管理员：问题管理 ----------

@router.get("", dependencies=[Depends(require_admin)])
async def list_questions(
    status: str | None = None,
    group_id: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    source_type: str | None = None,
    sort: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    limit = min(max(limit, 1), 500)
    return await qs.list_questions(
        status=status, group_id=group_id, search=search,
        date_from=date_from, source_type=source_type, sort=sort,
        limit=limit, offset=offset,
    )


@router.get("/{question_id}", dependencies=[Depends(require_admin)])
async def get_question(question_id: str):
    q = await qs.get_question(question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="问题不存在")
    return q


@router.patch("/{question_id}", dependencies=[Depends(require_admin)])
async def update_question(question_id: str, body: QuestionUpdateBody):
    try:
        return await qs.update_question(
            question_id,
            status=body.status,
            standard_answer=body.standard_answer,
            group_id=body.group_id,
            assignee=body.assignee,
            question_text=body.question,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{question_id}", dependencies=[Depends(require_admin)])
async def delete_question(question_id: str):
    await qs.delete_question(question_id)
    return {"ok": True}


# ---------- 分组 ----------


@groups_router.get("")
async def list_groups():
    return await qs.list_groups()


@groups_router.post("")
async def create_group(body: QuestionGroupBody):
    try:
        return await qs.create_group(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@groups_router.patch("/{group_id}")
async def rename_group(group_id: str, body: QuestionGroupBody):
    try:
        return await qs.rename_group(group_id, body.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@groups_router.delete("/{group_id}")
async def delete_group(group_id: str):
    await qs.delete_group(group_id)
    return {"ok": True}


# ---------- 后台概览（侧边栏 Badge / 首页提示） ----------


@overview_router.get("/overview")
async def admin_overview():
    """管理后台计数：待处理问题 / 无法回答消息数 / 解析失败文档数。"""
    db = get_db()
    q_row = await db.execute_fetchone(
        "SELECT COUNT(*) AS c FROM questions WHERE status='pending'"
    )
    u_row = await db.execute_fetchone(
        "SELECT COUNT(*) AS c FROM messages WHERE role='assistant' AND answer_status='insufficient_knowledge'"
    )
    p_row = await db.execute_fetchone(
        "SELECT COUNT(*) AS c FROM documents WHERE status='error' OR sync_status='failed'"
    )
    total_q = await db.execute_fetchone("SELECT COUNT(*) AS c FROM questions")
    return {
        "pending_questions": q_row["c"] if q_row else 0,
        "unanswered_messages": u_row["c"] if u_row else 0,
        "parse_failed_documents": p_row["c"] if p_row else 0,
        "total_questions": total_q["c"] if total_q else 0,
    }