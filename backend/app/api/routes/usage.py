"""用户端 Token 用量统计 API（仅统计当前登录用户）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.user_auth import get_current_user
from app.db.database import get_db

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
async def recent_usage(limit: int = 200, user: dict = Depends(get_current_user)):
    db = get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM token_usage WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user["id"], min(limit, 1000)),
    )
    return [dict(r) for r in rows]


@router.get("/summary")
async def usage_summary(user: dict = Depends(get_current_user)):
    db = get_db()
    rows = await db.execute_fetchall(
        "SELECT call_type, COUNT(*) AS calls, SUM(prompt_tokens) AS prompt_tokens, "
        "SUM(completion_tokens) AS completion_tokens, SUM(total_tokens) AS total_tokens, "
        "AVG(latency_ms) AS avg_latency_ms "
        "FROM token_usage WHERE user_id=? GROUP BY call_type ORDER BY total_tokens DESC",
        (user["id"],),
    )
    total_row = await db.execute_fetchone(
        "SELECT COUNT(*) AS calls, COALESCE(SUM(total_tokens),0) AS total_tokens "
        "FROM token_usage WHERE user_id=?",
        (user["id"],),
    )
    return {
        "by_call_type": [dict(r) for r in rows],
        "total": {
            "calls": total_row["calls"] if total_row else 0,
            "total_tokens": total_row["total_tokens"] if total_row else 0,
        },
    }
