"""问题库服务：知识缺口管理。

概念：Question Library 收集「知识库无法可靠回答的问题」，与聊天记录分离。
- 用户主动提交后才进入问题库（无法回答 ≠ 自动入库）。
- 重复问题通过「规范化 + 文本相似度」合并为 Canonical Question，累计出现次数。
- 删除分组不删除问题（group_id 置空，显示为未分类）。
"""
from __future__ import annotations

import difflib
import json
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.db.database import get_db
from app.prompts import question_group_suggester
from app.services.llm.client import LLMClient, LLMError, LLMNotConfiguredError
from app.utils.ids import new_id

logger = get_logger(__name__)

# 问题状态（稳定枚举，前端负责中文展示）
QUESTION_STATUS_PENDING = "pending"
QUESTION_STATUS_PROCESSING = "processing"
QUESTION_STATUS_RESOLVED = "resolved"
QUESTION_STATUS_ARCHIVED = "archived"
QUESTION_STATUSES = (
    QUESTION_STATUS_PENDING,
    QUESTION_STATUS_PROCESSING,
    QUESTION_STATUS_RESOLVED,
    QUESTION_STATUS_ARCHIVED,
)

# 相似度阈值：>= 视为同一问题（合并出现次数）
DEDUPE_THRESHOLD = 0.82
# 去重扫描上限（只比较最近 N 条，控制成本）
DEDUPE_SCAN_LIMIT = 500
# 复发催办阈值：occurrence_count 达到该值且非 pending 时高亮（M2）
RECUR_THRESHOLD = 3

# 规范化时剔除的空白与标点（全角空格用 chr(0x3000) 表示）
_PUNCT_CHARS = set(
    " " + chr(9) + chr(10) + chr(13) + chr(0x3000)
    + "，。！？、；：,.!?;:'\"()（）【】《》"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_question(text: str) -> str:
    """规范化问题文本：去空白/标点/小写，用于去重比较。"""
    if not text:
        return ""
    return "".join(ch for ch in text.lower() if ch not in _PUNCT_CHARS)


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _decode(raw) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(x) for x in data] if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _encode(items: list[str]) -> str:
    return json.dumps(items, ensure_ascii=False)


async def find_canonical_question(question: str) -> dict | None:
    """查找已有相同/相似问题。返回 questions 行或 None。"""
    db = get_db()
    norm = normalize_question(question)
    if not norm:
        return None
    rows = await db.execute_fetchall(
        "SELECT id, question, original_questions, occurrence_count, status "
        "FROM questions ORDER BY created_at DESC LIMIT ?",
        (DEDUPE_SCAN_LIMIT,),
    )
    for row in rows:
        if normalize_question(row["question"]) == norm:
            return dict(row)
    for row in rows:
        if _similarity(norm, normalize_question(row["question"])) >= DEDUPE_THRESHOLD:
            return dict(row)
    return None


async def submit_question(
    *,
    question: str,
    user_id: str | None,
    conversation_id: str,
    message_id: str,
    ai_answer: str | None = None,
    answer_status: str = "insufficient_knowledge",
    retrieval_snapshot: dict | None = None,
    model: str | None = None,
    feedback_type: str = "insufficient",
    feedback_note: str | None = None,
    context_snapshot: dict | None = None,
) -> dict:
    """用户提交问题到问题库。

    同一 message_id 重复提交幂等（返回已有记录）。
    相似问题合并：occurrence_count+1，原始提问追加。
    feedback_type: insufficient（无法回答）/ wrong_answer（回答有误）。
    context_snapshot: 提交时固化的来源会话上下文（防删除会话后追溯断裂）。
    """
    db = get_db()
    question = (question or "").strip()
    if not question:
        raise ValueError("问题不能为空")
    if feedback_type not in ("insufficient", "wrong_answer"):
        raise ValueError("非法反馈类型")

    # 幂等：同一来源消息已提交过
    existing = await db.execute_fetchone(
        "SELECT id FROM questions WHERE source_message_id=? LIMIT 1", (message_id,)
    )
    if existing:
        return {"question_id": existing["id"], "created": False, "merged": False}

    canonical = await find_canonical_question(question)
    now = _now_iso()
    if canonical is not None:
        originals = _decode(canonical["original_questions"])
        if question not in originals:
            originals.append(question)
        new_status = canonical["status"]
        # 归档或已解答问题再次出现 → 重新待处理（已解答说明知识库仍未补上）
        if canonical["status"] in (QUESTION_STATUS_ARCHIVED, QUESTION_STATUS_RESOLVED):
            new_status = QUESTION_STATUS_PENDING
        await db.execute(
            "UPDATE questions SET original_questions=?, occurrence_count=occurrence_count+1, "
            "status=?, updated_at=? WHERE id=?",
            (_encode(originals), new_status, now, canonical["id"]),
        )
        await db.commit()
        logger.info(
            "问题合并: question_id=%s new=%s occurrence=%d",
            canonical["id"], question, len(originals),
        )
        return {"question_id": canonical["id"], "created": False, "merged": True}

    qid = new_id("q_")
    # M2-Q05：LLM/规则自动分组建议（失败静默回退，不阻塞提交）
    suggestion = await suggest_group_for_question(question)
    suggested_gid = suggestion.get("group_id")
    suggested_reason = suggestion.get("reason") or ""
    await db.execute(
        "INSERT INTO questions(id, question, original_questions, occurrence_count, status, "
        "user_id, source_conversation_id, source_message_id, ai_answer, answer_status, "
        "retrieval_snapshot, model, feedback_type, feedback_note, context_snapshot, "
        "suggested_group_id, suggested_reason, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            qid,
            question,
            _encode([question]),
            1,
            QUESTION_STATUS_PENDING,
            user_id,
            conversation_id,
            message_id,
            ai_answer,
            answer_status,
            json.dumps(retrieval_snapshot or {}, ensure_ascii=False),
            model,
            feedback_type,
            feedback_note,
            json.dumps(context_snapshot or {}, ensure_ascii=False),
            suggested_gid,
            suggested_reason,
            now,
            now,
        ),
    )
    await db.commit()
    logger.info(
        "问题提交: question_id=%s user=%s conv=%s msg=%s type=%s question=%s",
        qid, user_id, conversation_id, message_id, feedback_type, question,
    )
    return {"question_id": qid, "created": True, "merged": False}


async def check_submitted(message_id: str) -> dict:
    """查询某条消息是否已提交问题库（用户端幂等展示用）。"""
    db = get_db()
    row = await db.execute_fetchone(
        "SELECT id, status, standard_answer, processed_at, feedback_type "
        "FROM questions WHERE source_message_id=? LIMIT 1",
        (message_id,),
    )
    if row is None:
        return {"submitted": False, "question_id": None, "status": None,
                "standard_answer": None, "processed_at": None}
    return {
        "submitted": True,
        "question_id": row["id"],
        "status": row["status"],
        "standard_answer": row["standard_answer"],
        "processed_at": row["processed_at"],
        "feedback_type": row["feedback_type"],
    }


async def list_questions(
    *,
    status: str | None = None,
    group_id: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    source_type: str | None = None,  # M2-Q06: insufficient | wrong_answer | model_error | retrieval_error
    sort: str | None = None,         # M2-Q09: created | hot（高频优先）
    limit: int = 200,
    offset: int = 0,
) -> dict:
    db = get_db()
    where: list[str] = []
    params: list = []
    if status and status != "all":
        where.append("q.status=?")
        params.append(status)
    if group_id:
        if group_id == "none":
            where.append("q.group_id IS NULL")
        else:
            where.append("q.group_id=?")
            params.append(group_id)
    if search and search.strip():
        where.append("(q.question LIKE ? OR q.original_questions LIKE ?)")
        params.extend([f"%{search.strip()}%", f"%{search.strip()}%"])
    if date_from:
        where.append("q.created_at >= ?")
        params.append(date_from)
    # M2-Q06：来源类型筛选（answer_status 覆盖模型/检索错误；feedback_type 覆盖知识不足/回答有误）
    if source_type and source_type != "all":
        if source_type in ("insufficient", "wrong_answer"):
            where.append("q.feedback_type=?")
            params.append(source_type)
        elif source_type in ("model_error", "retrieval_error"):
            where.append("q.answer_status=?")
            params.append(source_type)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    count_row = await db.execute_fetchone(
        f"SELECT COUNT(*) AS c FROM questions q {where_sql}", tuple(params)
    )
    # M2-Q09：hot 排序 = pending 优先 + 出现次数降序；默认 created_at DESC
    order_sql = (
        "ORDER BY (q.status='pending') DESC, q.occurrence_count DESC, q.created_at DESC"
        if sort == "hot"
        else "ORDER BY q.created_at DESC"
    )
    rows = await db.execute_fetchall(
        f"SELECT q.id, q.question, q.original_questions, q.occurrence_count, q.status, "
        f"q.group_id, g.name AS group_name, q.user_id, COALESCE(u.username, '（未知）') AS username, "
        f"q.source_conversation_id, q.source_message_id, q.answer_status, q.model, "
        f"q.assignee, q.created_at, q.updated_at, q.processed_at, q.feedback_type, q.feedback_note, "
        f"q.suggested_group_id, q.suggested_reason, q.standard_answer "
        f"FROM questions q "
        f"LEFT JOIN question_groups g ON g.id=q.group_id "
        f"LEFT JOIN users u ON u.id=q.user_id "
        f"{where_sql} {order_sql} LIMIT ? OFFSET ?",
        tuple(params) + (limit, offset),
    )
    status_rows = await db.execute_fetchall(
        "SELECT status, COUNT(*) AS c FROM questions GROUP BY status"
    )
    counts = {r["status"]: r["c"] for r in status_rows}
    counts["all"] = sum(counts.values())
    items = []
    for r in rows:
        d = dict(r)
        d["original_questions"] = _decode(d["original_questions"])
        # M2-Q08：复发标记（出现次数 >= 阈值 且 非待处理）
        d["is_recurring"] = (
            (d["occurrence_count"] or 0) >= RECUR_THRESHOLD
            and d["status"] != "pending"
        )
        items.append(d)
    return {"items": items, "counts": counts, "total": count_row["c"] if count_row else 0}


async def get_question(question_id: str, with_context: bool = True) -> dict | None:
    """问题详情。with_context 时附带来源会话的上下文消息（问题前后各 3 条）。

    优先读取提交时固化的 context_snapshot（删除会话/用户后仍可追溯）；
    快照缺失时回退实时查询来源会话。
    """
    db = get_db()
    row = await db.execute_fetchone(
        "SELECT q.*, g.name AS group_name, COALESCE(u.username, '（未知）') AS username "
        "FROM questions q "
        "LEFT JOIN question_groups g ON g.id=q.group_id "
        "LEFT JOIN users u ON u.id=q.user_id "
        "WHERE q.id=?",
        (question_id,),
    )
    if row is None:
        return None
    data = dict(row)
    data["original_questions"] = _decode(data["original_questions"])
    try:
        data["retrieval_snapshot"] = json.loads(data.get("retrieval_snapshot") or "{}")
    except json.JSONDecodeError:
        data["retrieval_snapshot"] = {}
    # 上下文：优先快照，其次实时会话
    if with_context:
        snapshot = None
        if data.get("context_snapshot"):
            try:
                snapshot = json.loads(data["context_snapshot"])
            except json.JSONDecodeError:
                snapshot = None
        if snapshot and snapshot.get("messages"):
            data["context"] = snapshot["messages"]
            data["context_source"] = "snapshot"
        elif data.get("source_conversation_id"):
            data["context"] = await _conversation_context(
                data["source_conversation_id"], data.get("source_message_id")
            )
            data["context_source"] = "live"
        else:
            data["context"] = []
            data["context_source"] = "none"
    else:
        data["context"] = []
    return data


async def build_context_snapshot(conv_id: str, around_msg_id: str | None, radius: int = 3) -> dict:
    """提交问题时固化来源会话上下文（前后各 radius 条），存入 questions.context_snapshot。

    会话/用户后续被删除后，问题详情仍可追溯来源上下文。
    """
    try:
        rows = await _conversation_context(conv_id, around_msg_id, radius=radius)
        return {"messages": rows, "captured_at": _now_iso()}
    except Exception as exc:
        logger.warning("上下文快照生成失败: %s", exc)
        return {"messages": [], "captured_at": _now_iso(), "error": str(exc)}


async def _conversation_context(conv_id: str, around_msg_id: str | None, radius: int = 3) -> list[dict]:
    """返回来源会话中，围绕 source_message 的前后消息（含其本身）。"""
    db = get_db()
    rows = await db.execute_fetchall(
        "SELECT id, role, content, answer_status, created_at "
        "FROM messages WHERE conversation_id=? ORDER BY created_at ASC",
        (conv_id,),
    )
    result = [dict(r) for r in rows]
    if not around_msg_id:
        return result[-radius * 2 :]
    idx = next((i for i, m in enumerate(result) if m["id"] == around_msg_id), None)
    if idx is None:
        return result[-radius * 2 :]
    lo = max(0, idx - radius)
    hi = min(len(result), idx + radius + 1)
    return result[lo:hi]


async def update_question(
    question_id: str,
    *,
    status: str | None = None,
    standard_answer: str | None = None,
    group_id: str | None = None,
    assignee: str | None = None,
    question_text: str | None = None,
) -> dict:
    db = get_db()
    row = await db.execute_fetchone("SELECT * FROM questions WHERE id=?", (question_id,))
    if row is None:
        raise KeyError(f"问题不存在: {question_id}")
    now = _now_iso()
    sets: list[str] = []
    params: list = []
    if status is not None:
        if status not in QUESTION_STATUSES:
            raise ValueError(f"非法状态: {status}")
        sets.append("status=?")
        params.append(status)
        if status == QUESTION_STATUS_RESOLVED:
            sets.append("processed_at=?")
            params.append(now)
    if standard_answer is not None:
        sets.append("standard_answer=?")
        params.append(standard_answer.strip() or None)
    if assignee is not None:
        sets.append("assignee=?")
        params.append(assignee.strip() or None)
    if question_text is not None and question_text.strip():
        sets.append("question=?")
        params.append(question_text.strip())
    if group_id is not None:
        if group_id == "" or group_id == "none":
            sets.append("group_id=NULL")
        else:
            g = await db.execute_fetchone("SELECT id FROM question_groups WHERE id=?", (group_id,))
            if g is None:
                raise ValueError("分组不存在")
            sets.append("group_id=?")
            params.append(group_id)
    if not sets:
        return await get_question(question_id, with_context=False)
    sets.append("updated_at=?")
    params.append(now)
    params.append(question_id)
    await db.execute(
        f"UPDATE questions SET {', '.join(sets)} WHERE id=?", tuple(params)
    )
    await db.commit()
    logger.info("问题更新: question_id=%s fields=%s", question_id, sets)
    return await get_question(question_id, with_context=False)


async def delete_question(question_id: str) -> None:
    db = get_db()
    await db.execute("DELETE FROM questions WHERE id=?", (question_id,))
    await db.commit()
    logger.info("问题已删除: question_id=%s", question_id)


# ---------- 问题分组 ----------


async def list_groups() -> list[dict]:
    db = get_db()
    rows = await db.execute_fetchall(
        "SELECT g.id, g.name, g.created_at, g.updated_at, "
        "(SELECT COUNT(*) FROM questions q WHERE q.group_id=g.id) AS question_count "
        "FROM question_groups g ORDER BY g.created_at ASC"
    )
    return [dict(r) for r in rows]


async def suggest_group_for_question(question: str) -> dict:
    """M2-Q05：为问题建议最匹配的分组。

    策略：先用关键词规则匹配（零成本、可解释）；规则未命中时用 LLM
    按已有分组名做意图分类（结构化输出）；LLM 不可用/无分组时静默回退。
    返回 {"group_id": str|None, "reason": str}。
    """
    db = get_db()
    question = (question or "").strip()
    if not question:
        return {"group_id": None, "reason": ""}
    groups = await list_groups()
    if not groups:
        return {"group_id": None, "reason": "暂无分组"}

    # 1) 规则匹配：问题包含分组名关键词（长度≥2 的组名直接命中）
    for g in groups:
        name = (g.get("name") or "").strip()
        if len(name) >= 2 and name in question:
            return {"group_id": g["id"], "reason": f"问题包含分组名「{name}」"}

    # 2) LLM 增强（结构化输出，失败静默回退）
    try:
        llm = LLMClient()
        system, user = question_group_suggester.build(question, groups)
        data = await llm.structured_object(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            call_type="question_group_suggester",
            temperature=0.0,
            max_tokens=200,
        )
        gid = data.get("group_id")
        confidence = float(data.get("confidence") or 0)
        reason = str(data.get("reason") or "")
        valid_ids = {g["id"] for g in groups}
        if gid in valid_ids and confidence >= 0.6:
            return {"group_id": gid, "reason": reason or "LLM 自动建议"}
        return {"group_id": None, "reason": ""}
    except (LLMNotConfiguredError, LLMError, ValueError, Exception):
        # 静默回退：LLM 不可用/超时/解析失败 → 不阻塞提交
        logger.debug("分组建议 LLM 不可用，跳过: %s", question[:30])
        return {"group_id": None, "reason": ""}


async def create_group(name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("分组名称不能为空")
    db = get_db()
    exists = await db.execute_fetchone("SELECT id FROM question_groups WHERE name=?", (name,))
    if exists:
        raise ValueError("分组名称已存在")
    gid = new_id("qg_")
    now = _now_iso()
    await db.execute(
        "INSERT INTO question_groups(id, name, created_at, updated_at) VALUES(?,?,?,?)",
        (gid, name, now, now),
    )
    await db.commit()
    logger.info("问题分组创建: id=%s name=%s", gid, name)
    return {"id": gid, "name": name, "created_at": now, "updated_at": now, "question_count": 0}


async def rename_group(group_id: str, name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("分组名称不能为空")
    db = get_db()
    row = await db.execute_fetchone("SELECT id FROM question_groups WHERE id=?", (group_id,))
    if row is None:
        raise KeyError("分组不存在")
    await db.execute(
        "UPDATE question_groups SET name=?, updated_at=? WHERE id=?",
        (name, _now_iso(), group_id),
    )
    await db.commit()
    return await list_groups()


async def delete_group(group_id: str) -> None:
    """删除分组：问题保留（FK ON DELETE SET NULL → 未分类）。"""
    db = get_db()
    await db.execute("DELETE FROM question_groups WHERE id=?", (group_id,))
    await db.commit()
    logger.info("问题分组已删除: id=%s（问题保留为未分类）", group_id)
