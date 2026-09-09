"""普通用户管理服务：增删改查、认证。"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.logging import get_logger
from app.core.user_auth import hash_password, verify_password
from app.db.database import get_db
from app.utils.ids import new_id

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_user(username: str, password: str, display_name: str | None = None) -> dict:
    """创建普通用户。用户名重复或参数不合法时抛 ValueError。"""
    username = (username or "").strip()
    if not (2 <= len(username) <= 32):
        raise ValueError("用户名长度需在 2-32 个字符之间")
    # 密码不做长度限制（可随意设置）
    db = get_db()
    row = await db.execute_fetchone("SELECT id FROM users WHERE username=?", (username,))
    if row is not None:
        raise ValueError("用户名已存在")
    user_id = new_id("user_")
    now = _now_iso()
    await db.execute(
        "INSERT INTO users(id, username, password_hash, display_name, is_active, created_at, updated_at) "
        "VALUES(?,?,?,?,1,?,?)",
        (user_id, username, hash_password(password), display_name or username, now, now),
    )
    await db.commit()
    return {"id": user_id, "username": username, "display_name": display_name or username}


async def delete_user(user_id: str) -> None:
    """删除用户：同时删除其对话（消息级联删除），用量与文档归属置空。"""
    db = get_db()
    await db.execute("UPDATE token_usage SET user_id=NULL WHERE user_id=?", (user_id,))
    await db.execute("DELETE FROM conversations WHERE user_id=?", (user_id,))
    await db.execute("UPDATE documents SET user_id=NULL WHERE user_id=?", (user_id,))
    await db.execute("DELETE FROM users WHERE id=?", (user_id,))
    await db.commit()


async def reset_password(user_id: str, new_password: str) -> None:
    # 密码不做长度限制（可随意设置）
    db = get_db()
    await db.execute(
        "UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
        (hash_password(new_password), _now_iso(), user_id),
    )
    await db.commit()


async def get_user_by_id(user_id: str) -> dict | None:
    db = get_db()
    row = await db.execute_fetchone(
        "SELECT id, username, display_name, is_active, created_at FROM users WHERE id=?",
        (user_id,),
    )
    return dict(row) if row else None


async def get_user_by_username(username: str) -> dict | None:
    db = get_db()
    row = await db.execute_fetchone(
        "SELECT id, username, password_hash, display_name, is_active, created_at "
        "FROM users WHERE username=?",
        ((username or "").strip(),),
    )
    return dict(row) if row else None


async def authenticate(username: str, password: str) -> dict | None:
    """校验用户名密码。成功返回用户（含 password_hash）；失败返回 None；被禁用抛 PermissionError。"""
    user = await get_user_by_username(username)
    if user is None or not verify_password(password, user["password_hash"]):
        return None
    if not user.get("is_active"):
        raise PermissionError("账号已被禁用")
    return user


async def list_users() -> list[dict]:
    """列出全部用户，附带对话数、用量汇总与最后活跃时间。"""
    db = get_db()
    rows = await db.execute_fetchall(
        "SELECT u.id, u.username, u.display_name, u.is_active, u.created_at, u.updated_at, "
        "(SELECT COUNT(*) FROM conversations c WHERE c.user_id=u.id) AS conversation_count, "
        "(SELECT COUNT(*) FROM token_usage t WHERE t.user_id=u.id) AS call_count, "
        "(SELECT COALESCE(SUM(t.total_tokens),0) FROM token_usage t WHERE t.user_id=u.id) AS total_tokens, "
        "(SELECT MAX(t.created_at) FROM token_usage t WHERE t.user_id=u.id) AS last_active "
        "FROM users u ORDER BY u.created_at DESC"
    )
    return [dict(r) for r in rows]
