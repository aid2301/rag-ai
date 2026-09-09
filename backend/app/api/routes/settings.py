"""设置与 LLM 连接测试 API（需管理员权限）。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI, OpenAIError

from app.core.admin import require_admin
from app.schemas.api import SettingsUpdate
from app.services import settings_service
from app.services.settings_service import LLMConfig

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/public")
async def get_public_settings():
    """用户端可读的非敏感设置（默认回答模式 / 是否显示思考过程）。"""
    return await settings_service.get_public()


@router.get("", dependencies=[Depends(require_admin)])
async def get_settings():
    return await settings_service.get_all()


@router.put("", dependencies=[Depends(require_admin)])
async def update_settings(body: SettingsUpdate):
    data = body.model_dump(exclude_none=True)
    try:
        return await settings_service.update(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"保存失败: {exc}")


@router.post("/test", dependencies=[Depends(require_admin)])
async def test_llm(body: SettingsUpdate | None = None):
    """用给定配置（或当前配置）发送一条测试消息。"""
    current = await settings_service.get_llm_config()
    cfg = LLMConfig(
        base_url=(body.llm_base_url if body and body.llm_base_url else current.base_url) or "",
        api_key=(body.llm_api_key if body and body.llm_api_key else current.api_key) or "",
        model=(body.llm_model if body and body.llm_model else current.model) or "",
        timeout=10.0,
        temperature=0.0,
        max_tokens=32,
    )
    if not cfg.configured:
        raise HTTPException(status_code=400, detail="请先填写 Base URL / API Key / Model")
    try:
        client = AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=cfg.timeout, max_retries=1)
        start = time.perf_counter()
        resp = await client.chat.completions.create(
            model=cfg.model,
            messages=[{"role": "user", "content": "你好"}],
            max_tokens=cfg.max_tokens,
        )
        latency = round((time.perf_counter() - start) * 1000, 0)
        reply = (resp.choices[0].message.content or "").strip()[:50]
        return {"ok": True, "model": cfg.model, "latency_ms": latency, "reply": reply}
    except OpenAIError as exc:
        raise HTTPException(status_code=400, detail=f"连接失败: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"连接失败: {exc}")