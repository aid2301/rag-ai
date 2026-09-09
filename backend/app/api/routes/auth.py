"""普通用户登录 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.user_auth import create_user_token, get_current_user
from app.services import users

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


@router.post("/login")
async def login(body: LoginBody):
    try:
        user = await users.authenticate(body.username, body.password)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {
        "ok": True,
        "token": create_user_token(user["id"]),
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user.get("display_name") or user["username"],
        },
    }


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user
