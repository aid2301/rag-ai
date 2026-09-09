"""运行时设置存储。

LLM 等可变配置优先读取数据库 settings 表；未配置时回退到环境变量默认值。
API Key 通过 masked 形式返回，避免明文完整暴露。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any

from app.core.config import settings
from app.db.database import get_db

_LLM_KEYS = [
    "llm_base_url",
    "llm_api_key",
    "llm_model",
    "llm_timeout",
    "llm_temperature",
    "llm_max_tokens",
    # 回答策略（非 LLM 密钥，但走同一设置通道）
    "default_chat_mode",   # auto | fast | standard | deep
    "show_thinking",       # 1 | 0
]


@dataclass
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout: float = 60.0
    temperature: float = 0.1
    max_tokens: int = 2048

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


def _env_default(key: str) -> Any:
    mapping = {
        "llm_base_url": settings.llm_base_url,
        "llm_api_key": settings.llm_api_key,
        "llm_model": settings.llm_model,
        "llm_timeout": settings.llm_timeout,
        "llm_temperature": settings.llm_temperature,
        "llm_max_tokens": settings.llm_max_tokens,
        "default_chat_mode": settings.default_chat_mode,
        "show_thinking": "1" if settings.show_thinking else "0",
    }
    return mapping.get(key, "")


async def get_all() -> dict[str, Any]:
    db = get_db()
    rows = await db.execute_fetchall("SELECT key, value FROM settings")
    stored = {r["key"]: r["value"] for r in rows}
    result: dict[str, Any] = {}
    for key in _LLM_KEYS:
        raw = stored.get(key, _env_default(key))
        result[key] = _coerce(key, raw)
    # 对 api_key 做脱敏，且永不回传明文
    masked = ""
    if result.get("llm_api_key"):
        masked = mask_secret(str(result["llm_api_key"]))
        result["llm_api_key_set"] = True
    else:
        result["llm_api_key_set"] = False
    result["llm_api_key_masked"] = masked
    result["llm_api_key"] = ""  # 空表示「未修改」，前端不回显明文
    return result


async def get_public() -> dict[str, Any]:
    """用户端可读的非敏感设置（不包含 API Key/模型密钥）。"""
    db = get_db()
    rows = await db.execute_fetchall("SELECT key, value FROM settings")
    stored = {r["key"]: r["value"] for r in rows}
    mode = _coerce("default_chat_mode", stored.get("default_chat_mode", _env_default("default_chat_mode")))
    thinking = _coerce("show_thinking", stored.get("show_thinking", _env_default("show_thinking")))
    return {
        "default_chat_mode": mode,
        "show_thinking": thinking == "1",
    }


async def get_llm_config() -> LLMConfig:
    db = get_db()
    rows = await db.execute_fetchall("SELECT key, value FROM settings")
    stored = {r["key"]: r["value"] for r in rows}
    return LLMConfig(
        base_url=_str_or_env("llm_base_url", stored),
        api_key=_str_or_env("llm_api_key", stored),
        model=_str_or_env("llm_model", stored),
        timeout=float(_coerce("llm_timeout", stored.get("llm_timeout", _env_default("llm_timeout")))),
        temperature=float(_coerce("llm_temperature", stored.get("llm_temperature", _env_default("llm_temperature")))),
        max_tokens=int(_coerce("llm_max_tokens", stored.get("llm_max_tokens", _env_default("llm_max_tokens")))),
    )


async def update(values: dict[str, Any]) -> dict[str, Any]:
    """更新设置。api_key 传空字符串表示不修改；传非空表示覆盖。"""
    db = get_db()
    updates: dict[str, str] = {}
    for key in _LLM_KEYS:
        if key not in values:
            continue
        if key == "llm_api_key":
            if values[key] == "" or values[key] is None:
                continue  # 空值不改动现有 key
        updates[key] = _serialize(values[key])
    for key, val in updates.items():
        await db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
            (key, val),
        )
    await db.commit()
    return await get_all()


async def set_key(key: str, value: Any) -> None:
    await update({key: value})


def mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "••••••••"
    return secret[:4] + "••••••••" + secret[-4:]


def _str_or_env(key: str, stored: dict[str, str]) -> str:
    if key in stored and stored[key] != "":
        return stored[key]
    return str(_env_default(key))


def _coerce(key: str, raw: Any) -> Any:
    if raw is None or raw == "":
        if key in ("llm_timeout",):
            return float(_env_default(key))
        if key in ("llm_max_tokens",):
            return int(_env_default(key))
        return _env_default(key)
    if key == "llm_timeout":
        return float(raw)
    if key == "llm_max_tokens":
        return int(raw)
    if key == "llm_temperature":
        return float(raw)
    if key == "default_chat_mode":
        val = str(raw).strip().lower()
        return val if val in ("auto", "fast", "standard", "deep") else "auto"
    if key == "show_thinking":
        return "1" if str(raw) in ("1", "true", "True", "on", "yes") else "0"
    return raw


def _serialize(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)