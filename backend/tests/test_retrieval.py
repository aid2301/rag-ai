# All document content and business values in this file are fictional test fixtures.
"""检索与上下文构建测试（无需 LLM）。"""
from __future__ import annotations

import pytest

from app.db.database import close_db
from tests.db_helpers import init_db_for_test
from app.services import documents
from app.services.rag.context_builder import ContextBuilder
from app.services.retrieval.retriever import Retriever

DOC1 = """# 演示项目说明

## 一、项目范围

虚构的演示资料包含星桥项目与晨光项目。

## 二、星桥项目时长

1. 星桥项目默认时长为 30-45 分钟。
2. 预留比例为 10%。

## 三、晨光项目时长

1. 晨光项目默认时长为 15-25 分钟。
2. 预留比例为 15%。
"""

DOC2 = """# 演示日程与借用说明

## 1. 活动日程

### 1.1 开始时间

虚构演示日程为每周三 14:00 - 16:00。

### 1.2 入场

预约开始前 5 分钟可以入场。

## 2. 借用制度

借用编号以 DEMO2048 开头的特殊样品需演示管理员登记。
"""


@pytest.fixture
async def db():
    await init_db_for_test()
    yield
    await close_db()


async def _import(doc_text: str, filename: str) -> str:
    return await documents.import_document(filename, doc_text.encode("utf-8"))


async def test_import_and_retrieve(db):
    await _import(DOC1, "演示项目说明.md")
    await _import(DOC2, "演示日程与借用说明.md")

    docs = await documents.list_documents()
    assert len(docs) == 2
    assert all(d["status"] == "ready" for d in docs)

    # 精确匹配 + FTS：星桥项目时长
    retriever = Retriever()
    plan = {
        "standalone_query": "星桥项目时长多少",
        "keywords": ["星桥项目", "时长", "时长"],
        "entities": ["星桥项目"],
    }
    result = await retriever.retrieve(plan)
    assert result.candidates, "应有候选文档"
    top = result.candidates[0]
    assert "演示项目" in top.title or "演示项目" in (top.title or "")

    # 编号精确匹配 DEMO2048 应命中借用制度
    plan2 = {"standalone_query": "DEMO2048", "keywords": ["DEMO2048"], "entities": ["DEMO2048"]}
    result2 = await retriever.retrieve(plan2)
    assert any("借用" in c.title for c in result2.candidates)


async def test_context_builder_full_doc(db):
    doc_id = await _import(DOC1, "演示项目说明.md")
    docs_list = await documents.list_documents()
    doc = await documents.get_document(doc_id)

    builder = ContextBuilder()
    selected = [
        {
            "document_id": doc_id,
            "title": doc["title"],
            "full_text": doc["full_text"],
            "char_count": doc["char_count"],
        }
    ]
    ctx = await builder.build(selected, [], expand_neighbors=False)
    assert "[SOURCE 1]" in ctx.text
    assert "Document:" in ctx.text
    assert len(ctx.citations) == 1
    assert ctx.citations[0].document_id == doc_id


async def test_disabled_document_is_excluded_from_all_retrieval_paths(db):
    """停用文档的标题、章节正文和残留 FTS 索引都不能进入候选集。"""
    doc_id = await _import(DOC2, "演示日程与借用说明.md")
    await documents.set_document_status(doc_id, "disabled")

    retriever = Retriever()
    result = await retriever.retrieve(
        {
            "standalone_query": "DEMO2048 特殊样品",
            "keywords": ["DEMO2048", "特殊样品"],
            "entities": ["DEMO2048"],
        }
    )

    assert all(c.document_id != doc_id for c in result.candidates)
    assert all(s.document_id != doc_id for s in result.sections)


async def test_context_builder_citation_indexing(db):
    await _import(DOC1, "演示项目说明.md")
    await _import(DOC2, "演示日程与借用说明.md")
    docs_list = await documents.list_documents()

    selected = []
    for d in docs_list:
        full = await documents.get_document(d["id"])
        selected.append(
            {
                "document_id": d["id"],
                "title": d["title"],
                "full_text": full["full_text"],
                "char_count": d["char_count"],
            }
        )
    builder = ContextBuilder()
    ctx = await builder.build(selected, [], expand_neighbors=False)
    assert len(ctx.citations) == 2
    assert [c.index for c in ctx.citations] == [1, 2]


async def test_delete_document_cascades(db):
    doc_id = await _import(DOC1, "演示项目说明.md")
    await documents.delete_document(doc_id)
    assert await documents.get_document(doc_id) is None
    sections = await documents.get_document_sections(doc_id)
    assert sections == []
