"""管理员登录 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.admin import create_access_token, verify_admin_credentials
from app.schemas.api import AdminLogin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/login")
async def login(body: AdminLogin):
    if not verify_admin_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return {"ok": True, "token": create_access_token()}
