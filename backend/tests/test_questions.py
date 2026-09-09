# All document content and business values in this file are fictional test fixtures.
"""问题库与文档编辑/重解析测试（无需 LLM，画像走启发式回退）。"""
from __future__ import annotations

import pytest

from app.db.database import close_db
from tests.db_helpers import init_db_for_test
from app.services import documents, questions

DOC1 = """# 演示项目说明

## 一、项目范围

虚构的演示资料包含星桥项目与晨光项目。

## 二、星桥项目时长

1. 星桥项目默认时长为 30-45 分钟。
2. 预留比例为 10%。
"""


@pytest.fixture
async def db():
    await init_db_for_test()
    yield
    await close_db()


async def _import(doc_text: str, filename: str) -> str:
    return await documents.import_document(filename, doc_text.encode("utf-8"))


# ---------- 问题库 ----------


async def test_submit_question_creates(db):
    res = await questions.submit_question(
        question="星桥项目时长多少？",
        user_id="u1",
        conversation_id="conv1",
        message_id="msg1",
        ai_answer="当前知识库暂时没有找到足够的信息回答这个问题。",
        answer_status="insufficient_knowledge",
    )
    assert res["created"] is True
    q = await questions.get_question(res["question_id"], with_context=False)
    assert q["status"] == "pending"
    assert q["occurrence_count"] == 1
    assert q["source_message_id"] == "msg1"


async def test_submit_same_message_idempotent(db):
    r1 = await questions.submit_question(question="A 问题", user_id="u1", conversation_id="c", message_id="m1")
    r2 = await questions.submit_question(question="A 问题", user_id="u1", conversation_id="c", message_id="m1")
    assert r1["question_id"] == r2["question_id"]
    assert r2["created"] is False
    q = await questions.get_question(r1["question_id"], with_context=False)
    assert q["occurrence_count"] == 1


async def test_submit_similar_question_merges(db):
    r1 = await questions.submit_question(question="星桥项目时长多少？", user_id="u1", conversation_id="c", message_id="m1")
    r2 = await questions.submit_question(question="星桥项目时长多少分钟？", user_id="u1", conversation_id="c", message_id="m2")
    assert r1["question_id"] == r2["question_id"]
    assert r2["merged"] is True
    q = await questions.get_question(r1["question_id"], with_context=False)
    assert q["occurrence_count"] == 2
    assert len(q["original_questions"]) == 2


async def test_question_status_lifecycle(db):
    r = await questions.submit_question(question="测试问题", user_id="u1", conversation_id="c", message_id="m1")
    qid = r["question_id"]
    q = await questions.update_question(qid, status="processing", assignee="演示管理员")
    assert q["status"] == "processing"
    assert q["assignee"] == "演示管理员"
    q = await questions.update_question(qid, status="resolved", standard_answer="默认 30-45")
    assert q["status"] == "resolved"
    assert q["processed_at"] is not None
    assert q["standard_answer"] == "默认 30-45"


async def test_group_delete_keeps_question(db):
    g = await questions.create_group("演示时长")
    r = await questions.submit_question(question="时长问题", user_id="u1", conversation_id="c", message_id="m1")
    qid = r["question_id"]
    await questions.update_question(qid, group_id=g["id"])
    q = await questions.get_question(qid, with_context=False)
    assert q["group_name"] == "演示时长"
    await questions.delete_group(g["id"])
    q = await questions.get_question(qid, with_context=False)
    assert q["group_id"] is None
    assert q["group_name"] is None


async def test_list_counts_and_filters(db):
    await questions.submit_question(question="问题一", user_id="u1", conversation_id="c", message_id="m1")
    await questions.submit_question(question="问题二", user_id="u1", conversation_id="c", message_id="m2")
    await questions.update_question(
        (await questions.find_canonical_question("问题二"))["id"], status="resolved"
    )
    res = await questions.list_questions()
    assert res["total"] == 2
    assert res["counts"]["pending"] == 1
    assert res["counts"]["resolved"] == 1
    pending = await questions.list_questions(status="pending")
    assert len(pending["items"]) == 1
    assert pending["items"][0]["question"] == "问题一"


# ---------- 文档编辑 / 重解析 ----------


async def test_import_then_edit_then_reparse(db):
    doc_id = await _import(DOC1, "演示项目说明.md")
    doc = await documents.get_document(doc_id)
    assert doc["status"] == "ready"
    assert doc["content_version"] == 1
    assert doc["index_version"] == 1
    assert doc["sync_status"] == "synced"

    # 编辑正文 → 待重新解析
    new_text = DOC1.replace("30-45", "40-60")
    doc = await documents.update_document_content(doc_id, title="演示项目说明", full_text=new_text)
    assert doc["content_version"] == 2
    assert doc["sync_status"] == "pending_reparse"
    assert "40-60" in doc["full_text"]

    # 重解析 → 使用当前知识正文，不覆盖编辑内容
    await documents.reprocess_document(doc_id)
    doc = await documents.get_document(doc_id)
    assert doc["status"] == "ready"
    assert doc["sync_status"] == "synced"
    assert doc["index_version"] == 2
    assert doc["content_version"] == 2
    assert "40-60" in doc["full_text"]

    # 检索章节应包含新内容
    sections = await documents.get_document_sections(doc_id)
    joined = " ".join(s["content"] for s in sections)
    assert "40-60" in joined


async def test_reparse_keeps_old_data_on_parse_failure(db):
    doc_id = await _import(DOC1, "演示项目说明.md")
    # 删除存储文件 → 重解析（未编辑，走文件解析）应失败但保留旧数据
    import os
    doc = await documents.get_document(doc_id)
    os.remove(doc["storage_path"])
    with pytest.raises(Exception):
        await documents.reprocess_document(doc_id)
    doc = await documents.get_document(doc_id)
    assert doc["sync_status"] == "failed"
    sections = await documents.get_document_sections(doc_id)
    assert len(sections) > 0  # 旧章节保留


async def test_generate_profile_status_machine(db):
    doc_id = await _import(DOC1, "演示项目说明.md")
    prof = await documents.get_document_profile(doc_id)
    assert prof["profile_status"] == "ready"
    assert prof["profile"] is not None
    # 重新生成
    prof = await documents.generate_document_profile(doc_id)
    assert prof["profile_status"] == "ready"


# ---------- M1：回答有误反馈 / resolved 复发回归 / 上下文快照 ----------


async def test_submit_wrong_answer_feedback(db):
    """Q-01：提交「回答有误」反馈，feedback_type/note 落库，check_submitted 返回状态。"""
    res = await questions.submit_question(
        question="借用额度是多少？",
        user_id="u1",
        conversation_id="conv1",
        message_id="msg_wrong1",
        ai_answer="借用额度 15 分钟。",
        answer_status="answered",
        feedback_type="wrong_answer",
        feedback_note="实际是 8000 分钟，回答过时了",
        context_snapshot={"messages": [{"role": "user", "content": "借用额度？"}], "captured_at": "x"},
    )
    assert res["created"] is True
    q = await questions.get_question(res["question_id"], with_context=False)
    assert q["feedback_type"] == "wrong_answer"
    assert q["feedback_note"] == "实际是 8000 分钟，回答过时了"

    st = await questions.check_submitted("msg_wrong1")
    assert st["submitted"] is True
    assert st["feedback_type"] == "wrong_answer"
    assert st["status"] == "pending"


async def test_submit_invalid_feedback_type_rejected(db):
    with pytest.raises(ValueError):
        await questions.submit_question(
            question="测试", user_id="u1", conversation_id="c", message_id="m_bad",
            feedback_type="bogus",
        )


async def test_resolved_question_recurrence_returns_pending(db):
    """Q-04：resolved 问题再次出现 → 回 pending（知识库仍未补上）。"""
    r1 = await questions.submit_question(question="借用期几天？", user_id="u1", conversation_id="c", message_id="m1")
    qid = r1["question_id"]
    await questions.update_question(qid, status="resolved", standard_answer="5 天")
    q = await questions.get_question(qid, with_context=False)
    assert q["status"] == "resolved"

    # 同义改写后再次提交（不同消息）→ 应合并并回 pending
    r2 = await questions.submit_question(question="借用期几天", user_id="u2", conversation_id="c2", message_id="m2")
    assert r2["question_id"] == qid
    assert r2["merged"] is True
    q = await questions.get_question(qid, with_context=False)
    assert q["status"] == "pending"
    assert q["occurrence_count"] == 2


async def test_context_snapshot_priority_over_deleted_conversation(db):
    """Q-16：详情优先读快照；删除会话后仍可追溯（快照优先于实时查询）。"""
    from app.db.database import get_db

    res = await questions.submit_question(
        question="宿舍怎么申请？",
        user_id="u1",
        conversation_id="conv_snap",
        message_id="msg_snap1",
        context_snapshot={
            "messages": [
                {"id": "m1", "role": "user", "content": "宿舍怎么申请？", "answer_status": None, "created_at": "t1"},
                {"id": "m2", "role": "assistant", "content": "当前知识库暂时没有找到足够的信息回答这个问题。", "answer_status": "insufficient_knowledge", "created_at": "t2"},
            ],
            "captured_at": "t2",
        },
    )
    q = await questions.get_question(res["question_id"], with_context=True)
    assert q["context_source"] == "snapshot"
    assert len(q["context"]) == 2
    assert q["context"][0]["content"] == "宿舍怎么申请？"

    # 模拟会话被删除后：快照仍可用
    conn = get_db()
    await conn.execute("DELETE FROM conversations WHERE id=?", ("conv_snap",))
    await conn.execute("DELETE FROM messages WHERE conversation_id=?", ("conv_snap",))
    await conn.commit()
    q = await questions.get_question(res["question_id"], with_context=True)
    assert q["context_source"] == "snapshot"
    assert len(q["context"]) == 2


async def test_list_includes_feedback_fields(db):
    """列表接口返回 feedback_type/feedback_note。"""
    await questions.submit_question(
        question="打卡规则？", user_id="u1", conversation_id="c", message_id="m1",
        feedback_type="wrong_answer", feedback_note="规则过时",
    )
    res = await questions.list_questions()
    assert res["total"] == 1
    assert res["items"][0]["feedback_type"] == "wrong_answer"
    assert res["items"][0]["feedback_note"] == "规则过时"


# ---------- M2：自动分组建议 / 来源筛选 / 高频排序 / 复发标记 ----------


async def test_suggest_group_rule_match(db):
    """Q-05：规则匹配——问题包含分组名时直接建议该分组。"""
    g = await questions.create_group("演示时长")
    sug = await questions.suggest_group_for_question("演示时长怎么算？")
    assert sug["group_id"] == g["id"]
    assert "演示时长" in sug["reason"]


async def test_suggest_group_llm_fallback_no_crash(db):
    """Q-05：无 LLM 配置或 LLM 不可用时静默回退，不抛错、不阻塞。"""
    g1 = await questions.create_group("日程")
    g2 = await questions.create_group("借用")
    # 不匹配规则 → 走 LLM；LLM 不可用（无配置）→ 回退 None
    sug = await questions.suggest_group_for_question("公司借用期有几天？")
    assert sug["group_id"] is None or sug["group_id"] in (g1["id"], g2["id"])
    # 提交时带上建议字段（即使为 None 也不报错）
    r = await questions.submit_question(
        question="公司借用期有几天？", user_id="u1", conversation_id="c", message_id="m_x"
    )
    q = await questions.get_question(r["question_id"], with_context=False)
    assert "suggested_group_id" in q


async def test_list_source_type_filter(db):
    """Q-06：按来源类型筛选。"""
    await questions.submit_question(
        question="A", user_id="u1", conversation_id="c", message_id="m1",
        feedback_type="wrong_answer", answer_status="answered",
    )
    await questions.submit_question(
        question="B", user_id="u1", conversation_id="c", message_id="m2",
        feedback_type="insufficient", answer_status="model_error",
    )
    wrong = await questions.list_questions(source_type="wrong_answer")
    assert wrong["total"] == 1
    assert wrong["items"][0]["question"] == "A"
    model = await questions.list_questions(source_type="model_error")
    assert model["total"] == 1
    assert model["items"][0]["question"] == "B"


async def test_list_hot_sort(db):
    """Q-09：hot 排序 = pending 优先 + 出现次数降序。"""
    # 两个 pending 问题：高频（3 次）应排前
    r1 = await questions.submit_question(question="借用期几天？", user_id="u1", conversation_id="c", message_id="m1")
    await questions.submit_question(question="借用期几天", user_id="u2", conversation_id="c2", message_id="m2")
    r3 = await questions.submit_question(question="借用期几天", user_id="u3", conversation_id="c3", message_id="m3")
    assert r3["question_id"] == r1["question_id"]
    await questions.submit_question(question="演示安排", user_id="u1", conversation_id="c4", message_id="m4")

    hot = await questions.list_questions(sort="hot")
    assert hot["total"] == 2
    # 高频问题应排最前（同为 pending 时 occurrence_count 降序）
    assert hot["items"][0]["question"].startswith("借用期")
    assert hot["items"][0]["occurrence_count"] == 3


async def test_recurring_flag(db):
    """Q-08：复发标记——occurrence_count>=3 且非 pending 时 is_recurring=True。"""
    r1 = await questions.submit_question(question="借用期几天？", user_id="u1", conversation_id="c", message_id="m1")
    await questions.submit_question(question="借用期几天", user_id="u2", conversation_id="c2", message_id="m2")
    r3 = await questions.submit_question(question="借用期几天", user_id="u3", conversation_id="c3", message_id="m3")
    assert r3["question_id"] == r1["question_id"]
    # pending 时不标记复发
    res = await questions.list_questions()
    row = next(x for x in res["items"] if x["id"] == r1["question_id"])
    assert row["is_recurring"] is False
    # 标记 resolved（非 pending）→ 复发标记生效
    await questions.update_question(r1["question_id"], status="resolved", standard_answer="5 天")
    res = await questions.list_questions()
    row = next(x for x in res["items"] if x["id"] == r1["question_id"])
    assert row["is_recurring"] is True
