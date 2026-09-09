"""LLM 用量收集的请求隔离测试。"""
from __future__ import annotations

import asyncio

from app.services.llm import client as client_module
from app.services.llm.client import LLMClient


class _FakeDb:
    async def execute(self, *_args, **_kwargs):
        return None

    async def commit(self):
        return None


async def test_usage_collectors_are_isolated_between_clients(monkeypatch):
    monkeypatch.setattr(client_module, "get_db", lambda: _FakeDb())
    first = LLMClient()
    second = LLMClient()

    await asyncio.gather(
        client_module._record_usage("analyze", "model-a", 10, 2, 12.5, first._usage),
        client_module._record_usage("answer", "model-b", 20, 5, 18.0, second._usage),
    )

    assert [item["call_type"] for item in first.collect_usage()] == ["analyze"]
    assert [item["call_type"] for item in second.collect_usage()] == ["answer"]

    # 返回快照而不是内部列表，调用方修改不会污染后续结果。
    snapshot = first.collect_usage()
    snapshot.clear()
    assert len(first.collect_usage()) == 1
