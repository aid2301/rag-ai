"""管理员账号密码认证。

内网管理后台用于统一配置 LLM API。
默认账号 admin，密码可通过环境变量 ADMIN_PASSWORD 设置；
未设置时固定为 admin123。

登录成功后返回的 access_token 有效期 7 天，
前端存在 localStorage，后续 /api/settings 与 /api/admin 请求需携带
Authorization: Bearer <token>。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import get_secret_key

logger = get_logger(__name__)

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"

# 统一签名密钥：环境变量 SECRET_KEY 优先，否则持久化到 data/secret_key（重启后 token 仍有效）
_SECRET = get_secret_key()
TOKEN_TTL_DAYS = 7


def _constant_time_equal(a: str, b: str) -> bool:
    """常量时间字符串比较。"""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_admin_credentials(username: str, password: str) -> bool:
    """校验管理员账号密码。"""
    expected_username = DEFAULT_USERNAME
    # 允许通过环境变量覆盖密码；环境变量为空则使用默认 admin123
    expected_password = settings.admin_password.strip() or DEFAULT_PASSWORD
    return (
        _constant_time_equal(username, expected_username)
        and _constant_time_equal(password, expected_password)
    )


def create_access_token() -> str:
    """创建登录成功后的 access_token。"""
    token = secrets.token_urlsafe(32)
    # domain 前缀（admin:）用于与用户 token 隔离：即使共享同一签名密钥，
    # 管理员 token 也无法通过用户 token 校验（防止 token 混淆提权）。
    expires_at = datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)
    payload = f"admin:{token}:{expires_at.timestamp()}"
    signature = hmac.new(_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    return f"{payload}:{signature}"


def verify_access_token(token: str | None) -> bool:
    """校验 access_token 是否有效且未过期。"""
    if not token:
        return False
    try:
        payload, signature = token.rsplit(":", 1)
        if not payload.startswith("admin:"):
            return False
        token_part, exp_ts = payload[len("admin:"):].rsplit(":", 1)
        exp_ts_float = float(exp_ts)
    except ValueError:
        return False

    expected_sig = hmac.new(_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(signature, expected_sig):
        return False

    if datetime.now(timezone.utc).timestamp() > exp_ts_float:
        return False

    # 简单校验：token_part 长度足够即可
    if len(token_part) < 32:
        return False
    return True


async def require_admin(authorization: str = Header(default="")) -> None:
    """FastAPI 依赖：校验 Authorization: Bearer <token> 请求头。"""
    token = ""
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not verify_access_token(token):
        raise HTTPException(status_code=403, detail="需要管理员权限")
