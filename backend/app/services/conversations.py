"""对话管理服务。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.db.database import get_db
from app.utils.ids import new_id

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_conversation(title: str | None = None, user_id: str | None = None) -> str:
    db = get_db()
    conv_id = new_id("conv_")
    now = _now_iso()
    await db.execute(
        "INSERT INTO conversations(id, title, user_id, created_at, updated_at) VALUES(?,?,?,?,?)",
        (conv_id, title or "新对话", user_id, now, now),
    )
    await db.commit()
    return conv_id


async def list_conversations(user_id: str | None = None) -> list[dict]:
    db = get_db()
    if user_id is not None:
        rows = await db.execute_fetchall(
            "SELECT c.id, c.title, c.created_at, c.updated_at, c.user_id, "
            "(SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) AS message_count "
            "FROM conversations c WHERE c.user_id=? ORDER BY c.updated_at DESC",
            (user_id,),
        )
    else:
        rows = await db.execute_fetchall(
            "SELECT c.id, c.title, c.created_at, c.updated_at, c.user_id, "
            "(SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) AS message_count "
            "FROM conversations c ORDER BY c.updated_at DESC"
        )
    return [dict(r) for r in rows]


async def get_message(message_id: str) -> dict | None:
    """按 id 读取单条消息（含解析后的 citations/debug_info/token_usage）。"""
    db = get_db()
    row = await db.execute_fetchone(
        "SELECT id, conversation_id, role, content, citations, debug_info, token_usage, "
        "answer_status, insufficient_reason, created_at FROM messages WHERE id=?",
        (message_id,),
    )
    if row is None:
        return None
    d = dict(row)
    for key in ("citations", "debug_info", "token_usage"):
        try:
            d[key] = json.loads(d.get(key) or "{}" if key != "citations" else d.get(key) or "[]")
        except json.JSONDecodeError:
            d[key] = [] if key == "citations" else {}
    return d


async def get_conversation(conv_id: str) -> dict | None:
    db = get_db()
    row = await db.execute_fetchone(
        "SELECT * FROM conversations WHERE id=?", (conv_id,)
    )
    if row is None:
        return None
    return dict(row)


async def delete_conversation(conv_id: str) -> None:
    db = get_db()
    await db.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    await db.commit()


async def rename_conversation(conv_id: str, title: str) -> None:
    db = get_db()
    await db.execute(
        "UPDATE conversations SET title=?, updated_at=? WHERE id=?",
        (title, _now_iso(), conv_id),
    )
    await db.commit()


async def add_message(
    conv_id: str,
    role: str,
    content: str,
    *,
    citations: list | None = None,
    debug_info: dict | None = None,
    token_usage: dict | None = None,
    answer_status: str = "answered",
    insufficient_reason: str | None = None,
) -> str:
    """保存一条消息。answer_status: answered / insufficient_knowledge / model_error / retrieval_error。"""
    db = get_db()
    msg_id = new_id("msg_")
    now = _now_iso()
    await db.execute(
        "INSERT INTO messages(id, conversation_id, role, content, citations, debug_info, "
        "token_usage, answer_status, insufficient_reason, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            msg_id,
            conv_id,
            role,
            content,
            json.dumps(citations or [], ensure_ascii=False),
            json.dumps(debug_info or {}, ensure_ascii=False),
            json.dumps(token_usage or {}, ensure_ascii=False),
            answer_status,
            insufficient_reason,
            now,
        ),
    )
    await db.execute(
        "UPDATE conversations SET updated_at=? WHERE id=?", (now, conv_id)
    )
    await db.commit()
    return msg_id


async def get_messages(conv_id: str, limit: int = 200) -> list[dict]:
    db = get_db()
    rows = await db.execute_fetchall(
        "SELECT id, role, content, citations, debug_info, token_usage, "
        "answer_status, insufficient_reason, created_at "
        "FROM messages WHERE conversation_id=? ORDER BY created_at ASC LIMIT ?",
        (conv_id, limit),
    )
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["citations"] = json.loads(d.get("citations") or "[]")
        except json.JSONDecodeError:
            d["citations"] = []
        try:
            d["debug_info"] = json.loads(d.get("debug_info") or "{}")
        except json.JSONDecodeError:
            d["debug_info"] = {}
        try:
            d["token_usage"] = json.loads(d.get("token_usage") or "{}")
        except json.JSONDecodeError:
            d["token_usage"] = {}
        result.append(d)
    return result


async def get_recent_messages(conv_id: str, limit: int = 6) -> list[dict]:
    rows = await get_messages(conv_id, limit=1000)
    return rows[-limit:]


async def get_summary(conv_id: str) -> str:
    db = get_db()
    row = await db.execute_fetchone(
        "SELECT summary FROM conversations WHERE id=?", (conv_id,)
    )
    return (row["summary"] if row and row["summary"] else "") or ""


async def set_summary(conv_id: str, summary: str) -> None:
    db = get_db()
    await db.execute(
        "UPDATE conversations SET summary=? WHERE id=?", (summary, conv_id)
    )
    await db.commit()


async def set_title_if_empty(conv_id: str, title: str) -> None:
    db = get_db()
    row = await db.execute_fetchone(
        "SELECT title FROM conversations WHERE id=?", (conv_id,)
    )
    if row and (not row["title"] or row["title"] == "新对话"):
        await db.execute(
            "UPDATE conversations SET title=? WHERE id=?", (title, conv_id)
        )
        await db.commit()