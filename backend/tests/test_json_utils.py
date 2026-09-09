"""JSON 解析工具测试。"""
from __future__ import annotations

import pytest

from app.utils.json_utils import extract_json, extract_json_object


def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json("[1, 2, 3]") == [1, 2, 3]


def test_extract_json_in_code_fence():
    text = '```json\n{"selected_documents": []}\n```'
    assert extract_json(text) == {"selected_documents": []}


def test_extract_json_with_surrounding_text():
    text = '好的，结果如下：\n{"confidence": 0.96}\n希望有帮助。'
    assert extract_json(text) == {"confidence": 0.96}


def test_extract_json_object_from_array():
    assert extract_json_object('[{"a": 1}, {"a": 2}]') == {"a": 1}


def test_extract_json_failure():
    with pytest.raises(ValueError):
        extract_json("这不是 JSON")
    with pytest.raises(ValueError):
        extract_json_object("[]")
