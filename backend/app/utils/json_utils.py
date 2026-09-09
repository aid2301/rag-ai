"""LLM 结构化输出解析工具。

LLM 输出的 JSON 常被包裹在 markdown 代码块中，或前后带有说明文字。
这里实现一个稳健的提取器，并支持单次自动修复（截断 JSON 补全）。
"""
from __future__ import annotations

import json
import re
from typing import Any

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """从 LLM 文本中提取 JSON 对象/数组。失败抛出 ValueError。"""
    if not text:
        raise ValueError("empty text")

    stripped = text.strip()
    # 1) 尝试整体解析
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 2) 提取 markdown 代码块
    m = _CODE_FENCE_RE.search(stripped)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3) 找到第一个 { 或 [ 并做平衡截取
    for start_ch, end_ch in (("{", "}"), ("[", "]")):
        start = stripped.find(start_ch)
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(stripped)):
            ch = stripped[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == start_ch:
                depth += 1
            elif ch == end_ch:
                depth -= 1
                if depth == 0:
                    candidate = stripped[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
    raise ValueError("no JSON object found")


def extract_json_object(text: str) -> dict[str, Any]:
    """提取 JSON 对象；若结果为数组则取第一个对象。"""
    data = extract_json(text)
    if isinstance(data, list):
        if not data:
            raise ValueError("empty JSON array")
        data = data[0]
    if not isinstance(data, dict):
        raise ValueError("JSON value is not an object")
    return data


def dumps_compact(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
