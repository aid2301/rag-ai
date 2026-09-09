"""管理后台：用户管理、用户用量统计、用户对话记录（需管理员权限）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.admin import require_admin
from app.db.database import get_db
from app.services import conversations, users

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-users"],
    dependencies=[Depends(require_admin)],
)


class UserCreateBody(BaseModel):
    username: str = Field(..., min_length=2, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)
    display_name: str | None = None


class ResetPasswordBody(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


@router.get("/users")
async def list_users():
    return await users.list_users()


@router.post("/users")
async def create_user(body: UserCreateBody):
    try:
        return await users.create_user(body.username, body.password, body.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/users/{user_id}")
async def delete_user(user_id: str):
    if await users.get_user_by_id(user_id) is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    await users.delete_user(user_id)
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: str, body: ResetPasswordBody):
    if await users.get_user_by_id(user_id) is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    try:
        await users.reset_password(user_id, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.get("/users/{user_id}/conversations")
async def list_user_conversations(user_id: str):
    if await users.get_user_by_id(user_id) is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return await conversations.list_conversations(user_id=user_id)


@router.get("/conversations")
async def list_all_conversations():
    """管理端：列出全部对话（含归属用户名，含历史无主对话）。"""
    db = get_db()
    rows = await db.execute_fetchall(
        "SELECT c.id, c.title, c.created_at, c.updated_at, c.user_id, "
        "COALESCE(u.username, '（历史无主）') AS username, "
        "(SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) AS message_count, "
        "(SELECT COUNT(*) FROM messages m2 WHERE m2.conversation_id=c.id "
        " AND m2.role='assistant' AND m2.answer_status='insufficient_knowledge') AS unanswered_count "
        "FROM conversations c LEFT JOIN users u ON u.id=c.user_id "
        "ORDER BY c.updated_at DESC"
    )
    return [dict(r) for r in rows]


@router.get("/conversations/{conv_id}/messages")
async def get_any_conversation_messages(conv_id: str):
    """管理端：查看任意对话的完整聊天记录（含回答状态与问题库关联）。"""
    conv = await conversations.get_conversation(conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    return await _messages_with_question_link(conv_id)


@router.get("/users/{user_id}/conversations/{conv_id}/messages")
async def get_user_conversation_messages(user_id: str, conv_id: str):
    conv = await conversations.get_conversation(conv_id)
    if conv is None or conv.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="对话不存在")
    return await _messages_with_question_link(conv_id)


async def _messages_with_question_link(conv_id: str) -> list[dict]:
    """消息列表 + 每条的 question_library 关联标记。"""
    db = get_db()
    msgs = await conversations.get_messages(conv_id)
    if not msgs:
        return msgs
    msg_ids = [m["id"] for m in msgs]
    q_rows = await db.execute_fetchall(
        "SELECT source_message_id, id, status FROM questions "
        "WHERE source_message_id = ANY($1::text[])",
        (msg_ids,),
    )
    link_by_msg: dict[str, dict] = {}
    for qr in q_rows:
        link_by_msg[qr["source_message_id"]] = {"question_id": qr["id"], "status": qr["status"]}
    for m in msgs:
        m["in_question_library"] = m["id"] in link_by_msg
        m["question_link"] = link_by_msg.get(m["id"])
    return msgs


@router.get("/usage")
async def admin_usage():
    """管理端用量统计：按用户汇总 + 按步骤汇总 + 最近记录。"""
    db = get_db()
    by_user = await db.execute_fetchall(
        "SELECT COALESCE(u.username, '（未知用户）') AS username, t.user_id, "
        "COUNT(*) AS calls, COALESCE(SUM(t.prompt_tokens),0) AS prompt_tokens, "
        "COALESCE(SUM(t.completion_tokens),0) AS completion_tokens, "
        "COALESCE(SUM(t.total_tokens),0) AS total_tokens, "
        "MAX(t.created_at) AS last_active "
        "FROM token_usage t LEFT JOIN users u ON u.id=t.user_id "
        "GROUP BY t.user_id, u.username ORDER BY total_tokens DESC"
    )
    by_call_type = await db.execute_fetchall(
        "SELECT call_type, COUNT(*) AS calls, COALESCE(SUM(prompt_tokens),0) AS prompt_tokens, "
        "COALESCE(SUM(completion_tokens),0) AS completion_tokens, "
        "COALESCE(SUM(total_tokens),0) AS total_tokens, AVG(latency_ms) AS avg_latency_ms "
        "FROM token_usage GROUP BY call_type ORDER BY total_tokens DESC"
    )
    total_row = await db.execute_fetchone(
        "SELECT COUNT(*) AS calls, COALESCE(SUM(total_tokens),0) AS total_tokens FROM token_usage"
    )
    recent = await db.execute_fetchall(
        "SELECT t.id, t.call_type, t.model, t.total_tokens, t.latency_ms, t.created_at, "
        "COALESCE(u.username, '（未知）') AS username "
        "FROM token_usage t LEFT JOIN users u ON u.id=t.user_id "
        "ORDER BY t.id DESC LIMIT 200"
    )
    return {
        "by_user": [dict(r) for r in by_user],
        "by_call_type": [dict(r) for r in by_call_type],
        "total": {
            "calls": total_row["calls"] if total_row else 0,
            "total_tokens": total_row["total_tokens"] if total_row else 0,
        },
        "recent": [dict(r) for r in recent],
    }