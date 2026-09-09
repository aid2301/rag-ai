"""LLM 统一调用封装。

业务层禁止直接使用 OpenAI SDK，统一通过 LLMClient。
所有调用记录 token 用量与延迟，方便分析各环节成本。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from openai import AsyncOpenAI, OpenAIError

from app.core.logging import get_logger
from app.core.user_auth import get_current_user_id
from app.db.database import get_db
from app.services import settings_service
from app.utils.json_utils import extract_json_object

logger = get_logger(__name__)

class LLMError(Exception):
    """LLM 调用失败（可被上层捕获并转为友好错误）。"""


class LLMNotConfiguredError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _record_usage(
    call_type: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    collector: list[dict] | None = None,
) -> None:
    usage = {
        "call_type": call_type,
        "model": model,
        "user_id": get_current_user_id(),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "latency_ms": round(latency_ms, 2),
        "created_at": _now_iso(),
    }
    if collector is not None:
        collector.append(usage)
    try:
        db = get_db()
        await db.execute(
            "INSERT INTO token_usage(call_type, model, user_id, prompt_tokens, completion_tokens, "
            "total_tokens, latency_ms, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                call_type,
                model,
                get_current_user_id(),
                prompt_tokens,
                completion_tokens,
                prompt_tokens + completion_tokens,
                round(latency_ms, 2),
                _now_iso(),
            ),
        )
        await db.commit()
    except Exception as exc:  # 记录失败不应影响主流程
        logger.warning("token 用量记录失败: %s", exc)


class LLMClient:
    def __init__(self) -> None:
        # LLMClient 由每条业务流水线独立创建；用量跟随实例，天然隔离并发请求。
        self._usage: list[dict] = []

    def collect_usage(self) -> list[dict]:
        return list(self._usage)

    def _build_client(self, cfg: settings_service.LLMConfig) -> AsyncOpenAI:
        return AsyncOpenAI(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            timeout=cfg.timeout,
            max_retries=1,
        )

    async def _complete(
        self,
        messages: list[dict[str, str]],
        *,
        call_type: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        stream: bool = False,
    ) -> Any:
        cfg = await settings_service.get_llm_config()
        if not cfg.configured:
            raise LLMNotConfiguredError("尚未配置 LLM（Base URL / API Key / Model）")

        client = self._build_client(cfg)
        kwargs: dict[str, Any] = {
            "model": cfg.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else cfg.temperature,
            "max_tokens": max_tokens if max_tokens is not None else cfg.max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if stream:
            kwargs["stream"] = True

        start = time.perf_counter()
        try:
            resp = await client.chat.completions.create(**kwargs)
        except OpenAIError as exc:
            elapsed = (time.perf_counter() - start) * 1000
            msg = str(exc)
            logger.error("LLM 调用失败[%s]: %s", call_type, msg)
            if "timed out" in msg.lower() or "timeout" in msg.lower():
                raise LLMTimeoutError("LLM 请求超时") from exc
            if json_mode:
                # 某些兼容服务不支持 json_object，回退重试一次
                logger.warning("json_mode 失败，回退普通模式重试: %s", msg)
                kwargs.pop("response_format", None)
                start2 = time.perf_counter()
                try:
                    resp = await client.chat.completions.create(**kwargs)
                except OpenAIError as exc2:
                    elapsed2 = (time.perf_counter() - start2) * 1000
                    await _record_usage(
                        call_type, cfg.model, 0, 0, elapsed + elapsed2, self._usage
                    )
                    raise LLMError(f"LLM 调用失败: {exc2}") from exc2
            else:
                await _record_usage(call_type, cfg.model, 0, 0, elapsed, self._usage)
                raise LLMError(f"LLM 调用失败: {exc}") from exc

        if stream:
            return resp
        elapsed = (time.perf_counter() - start) * 1000
        usage = getattr(resp, "usage", None)
        pt = getattr(usage, "prompt_tokens", 0) or 0
        ct = getattr(usage, "completion_tokens", 0) or 0
        await _record_usage(call_type, cfg.model, pt, ct, elapsed, self._usage)
        return resp

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        call_type: str = "chat",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        resp = await self._complete(
            messages, call_type=call_type, temperature=temperature, max_tokens=max_tokens
        )
        return resp.choices[0].message.content or ""

    async def structured_object(
        self,
        messages: list[dict[str, str]],
        *,
        call_type: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        schema_hint: str = "",
    ) -> dict[str, Any]:
        """返回 JSON 对象。解析失败时自动做一次修复调用。"""
        msgs = list(messages)
        if schema_hint:
            msgs.append({"role": "user", "content": schema_hint})
        try:
            text = await self.chat(
                msgs, call_type=call_type, temperature=temperature, max_tokens=max_tokens
            )
            return extract_json_object(text)
        except (LLMError, ValueError) as exc:
            if isinstance(exc, LLMError):
                raise
            logger.warning("JSON 解析失败，尝试修复: %s", exc)
            repair = list(messages) + [
                {"role": "assistant", "content": "（上次输出 JSON 无法解析）"},
                {
                    "role": "user",
                    "content": "你上一次的输出不是合法 JSON。请只输出一个合法 JSON 对象，"
                    "不要包含任何多余文字或代码块。",
                },
            ]
            if schema_hint:
                repair.append({"role": "user", "content": schema_hint})
            text = await self.chat(repair, call_type=f"{call_type}_repair", temperature=0.0)
            try:
                return extract_json_object(text)
            except ValueError as exc2:
                raise LLMError(f"LLM 结构化输出无法解析: {exc2}") from exc2

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        call_type: str = "answer",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """流式输出，逐段 yield 文本。"""
        cfg = await settings_service.get_llm_config()
        if not cfg.configured:
            raise LLMNotConfiguredError("尚未配置 LLM（Base URL / API Key / Model）")
        client = self._build_client(cfg)
        kwargs: dict[str, Any] = {
            "model": cfg.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else cfg.temperature,
            "max_tokens": max_tokens if max_tokens is not None else cfg.max_tokens,
            "stream": True,
        }
        start = time.perf_counter()
        pt = ct = 0
        try:
            stream = await client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if chunk.usage is not None:
                    pt = chunk.usage.prompt_tokens or 0
                    ct = chunk.usage.completion_tokens or 0
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except OpenAIError as exc:
            msg = str(exc)
            logger.error("LLM 流式调用失败[%s]: %s", call_type, msg)
            if "timed out" in msg.lower() or "timeout" in msg.lower():
                raise LLMTimeoutError("LLM 请求超时") from exc
            raise LLMError(f"LLM 调用失败: {exc}") from exc
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            await _record_usage(call_type, cfg.model, pt, ct, elapsed, self._usage)
