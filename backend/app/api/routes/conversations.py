"""对话管理 API（需普通用户登录）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.user_auth import get_current_user
from app.services import conversations

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class CreateBody(BaseModel):
    title: str | None = None


class RenameBody(BaseModel):
    title: str


async def _owned_conversation(conv_id: str, user_id: str) -> dict:
    """取当前用户拥有的对话，否则抛 404。"""
    conv = await conversations.get_conversation(conv_id)
    if conv is None or conv.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conv


@router.get("")
async def list_conversations(user: dict = Depends(get_current_user)):
    return await conversations.list_conversations(user_id=user["id"])


@router.post("")
async def create_conversation(body: CreateBody, user: dict = Depends(get_current_user)):
    conv_id = await conversations.create_conversation(body.title, user_id=user["id"])
    conv = await conversations.get_conversation(conv_id)
    return {"id": conv_id, **conv}


@router.get("/{conv_id}/messages")
async def get_messages(conv_id: str, user: dict = Depends(get_current_user)):
    await _owned_conversation(conv_id, user["id"])
    return await conversations.get_messages(conv_id)


@router.patch("/{conv_id}")
async def rename_conversation(conv_id: str, body: RenameBody, user: dict = Depends(get_current_user)):
    await _owned_conversation(conv_id, user["id"])
    await conversations.rename_conversation(conv_id, body.title)
    return {"ok": True}


@router.delete("/{conv_id}")
async def delete_conversation(conv_id: str, user: dict = Depends(get_current_user)):
    await _owned_conversation(conv_id, user["id"])
    await conversations.delete_conversation(conv_id)
    return {"ok": True}
