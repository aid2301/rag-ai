"""ID 生成工具。"""
from __future__ import annotations

import uuid


def new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex
    return f"{prefix}{raw}" if prefix else raw
