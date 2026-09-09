"""普通用户认证。

- 用户名密码登录（密码使用 PBKDF2-SHA256 加盐哈希存储）
- 登录成功后返回 HMAC access_token
- FastAPI 依赖 get_current_user / get_optional_user 用于用户端接口
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

from app.core.logging import get_logger
from app.core.security import get_secret_key
from app.db.database import get_db

logger = get_logger(__name__)

TOKEN_TTL_DAYS = 7
_PBKDF2_ITERATIONS = 100_000

# 统一签名密钥：环境变量 SECRET_KEY 优先，否则持久化到 data/secret_key（重启后 token 仍有效）
_SECRET = get_secret_key()

# ---- 请求级用户上下文：用于把 token 用量归属到当前用户 ----
_current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def set_current_user_id(user_id: str | None) -> None:
    _current_user_id.set(user_id)


def get_current_user_id() -> str | None:
    return _current_user_id.get()


# ---------- 密码哈希 ----------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ---------- 用户 access_token ----------


def create_user_token(user_id: str) -> str:
    """创建登录成功后的 access_token。"""
    expires_at = datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)
    # domain 前缀（user:）用于与管理员 token 隔离：即使共享同一签名密钥，
    # 用户 token 也无法通过管理员 token 校验（防止 token 混淆提权）。
    payload = f"user:{user_id}:{expires_at.timestamp()}"
    signature = hmac.new(
        _SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:16]
    return f"{payload}:{signature}"


def verify_user_token(token: str) -> str | None:
    """校验 access_token，返回 user_id；无效返回 None。"""
    try:
        payload, signature = token.rsplit(":", 1)
        if not payload.startswith("user:"):
            return None
        user_id, exp_ts = payload[len("user:"):].rsplit(":", 1)
        exp_ts_float = float(exp_ts)
    except ValueError:
        return None

    expected = hmac.new(
        _SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:16]
    if not hmac.compare_digest(signature, expected):
        return None
    if datetime.now(timezone.utc).timestamp() > exp_ts_float:
        return None
    if len(user_id) < 4:
        return None
    return user_id


def _extract_bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


async def _load_user(user_id: str) -> dict | None:
    db = get_db()
    row = await db.execute_fetchone(
        "SELECT id, username, display_name, is_active, created_at FROM users WHERE id=?",
        (user_id,),
    )
    return dict(row) if row else None


async def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI 依赖：校验用户 access_token，返回用户记录；未登录返回 401。"""
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    user_id = verify_user_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = await _load_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="账号已被禁用")
    set_current_user_id(user["id"])
    return user


async def get_optional_user(authorization: str | None = Header(default=None)) -> dict | None:
    """FastAPI 依赖：可选登录。带有效 token 时返回用户，否则返回 None。"""
    token = _extract_bearer(authorization)
    if not token:
        return None
    user_id = verify_user_token(token)
    if not user_id:
        return None
    user = await _load_user(user_id)
    if user is None or not user.get("is_active"):
        return None
    set_current_user_id(user["id"])
    return user
