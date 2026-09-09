"""文档管理服务：导入、解析、画像、编辑、FTS 索引、重解析、删除。

数据模型约定：
- `documents.full_text` 是「当前知识正文」，也是 RAG 的 Source of Truth。
  上传时 = 解析器提取的原文；管理员在线编辑后 = 编辑后的正文。
- 版本追踪：`content_version`（正文版本，编辑+1）、`index_version`（索引版本，
  重解析成功后 = content_version）。二者相等 ⇔ sync_status='synced'（已同步）；
  编辑后 sync_status='pending_reparse'（待重新解析）。
- 画像状态机：profile_status ∈ none/generating/ready/error，失败原因在 profile_error。
- 重解析数据源：若文档曾被在线编辑（edited_at 非空），从「当前知识正文」重新解析；
  否则从原始文件重新解析。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import get_db
from app.services.document_parser import parse_document
from app.services.document_parser.base import ParsedDocument
from app.services.document_parser.text_parser import parse_text
from app.services.llm.client import LLMClient, LLMError, LLMNotConfiguredError
from app.prompts import document_profiler as profiler_prompt
from app.utils.ids import new_id
from app.utils.text import tokenize_for_fts

logger = get_logger(__name__)

_CJK_RUN_RE = re.compile(r"[一-鿿]+")
_STOPWORDS = set("的了是在有和就不人都一一个上也很到说要去你会着没有看看好这那与及或并对于关于按照根据以及但是然而如果那么因为所以")

_PROFILE_CONTENT_MAX = 12000

# 画像状态
PROFILE_STATUS_NONE = "none"
PROFILE_STATUS_GENERATING = "generating"
PROFILE_STATUS_READY = "ready"
PROFILE_STATUS_ERROR = "error"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    name = "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in name)
    return name or "document"


def _extract_metadata(filename: str, title: str) -> dict:
    """启发式从文件名/标题提取版本与生效日期（用于冲突时的优先级判断）。"""
    meta: dict = {}
    text = f"{filename} {title or ''}"
    m = re.search(r"[vV]([0-9]+(?:[.][0-9]+)?)", text)
    if m:
        meta["version"] = m.group(1)
    elif re.search(r"修订|新版|旧版|最终版", text):
        meta["version"] = "修订版"
    m = re.search(r"(20[0-9]{2})", text)
    if m:
        meta["effective_date"] = m.group(1)
    return meta


def _parse_current_text(full_text: str, title: str) -> ParsedDocument:
    """从「当前知识正文」解析章节（编辑后的文档以此为准，避免旧文件覆盖新内容）。"""
    text = full_text or ""
    fd, tmp_path = tempfile.mkstemp(suffix=".md", prefix="kb_edit_", dir=str(settings.documents_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        filename = f"{title or 'knowledge'}.md"
        return parse_text(tmp_path, filename)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def import_document(filename: str, content: bytes, user_id: str | None = None) -> str:
    """保存文件、解析、入库、生成画像、建立 FTS 索引。返回 document_id。

    解析与文件写入为 CPU/IO 密集的同步操作，统一通过 asyncio.to_thread
    放到线程池执行，避免阻塞事件循环（大文档上传不拖垮其他请求）。
    """
    db = get_db()
    doc_id = new_id("doc_")
    safe_name = _safe_filename(filename)
    ext = Path(safe_name).suffix.lower()
    storage_name = f"{doc_id}_{safe_name}"
    storage_dir = Path(settings.documents_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / storage_name
    await asyncio.to_thread(storage_path.write_bytes, content)

    now = _now_iso()
    await db.execute(
        "INSERT INTO documents(id, filename, file_type, storage_path, status, user_id, created_at, updated_at, "
        "content_version, index_version, sync_status, profile_status, last_parsed_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            doc_id,
            safe_name,
            ext.lstrip("."),
            str(storage_path),
            "processing",
            user_id,
            now,
            now,
            1,  # content_version：导入即 v1
            1,  # index_version：首次导入即同步
            "synced",
            PROFILE_STATUS_GENERATING,
            now,
        ),
    )
    await db.commit()
    logger.info("文档上传: id=%s filename=%s", doc_id, safe_name)

    try:
        parsed = await asyncio.to_thread(parse_document, str(storage_path), safe_name)
        await _save_sections(doc_id, parsed, now)
        # 先建立无画像索引，保证检索可用；随后再生成画像并重建索引
        profile = await _generate_profile(doc_id, parsed.title, parsed.full_text)
        await _save_profile(doc_id, profile, now)
        await _index_fts(doc_id)
        meta = _extract_metadata(safe_name, parsed.title)
        await db.execute(
            "UPDATE documents SET title=?, full_text=?, char_count=?, section_count=?, "
            "metadata=?, status='ready', profile_status=?, profile_error=NULL, "
            "content_version=1, index_version=1, sync_status='synced', last_parsed_at=?, updated_at=? "
            "WHERE id=?",
            (
                parsed.title,
                parsed.full_text,
                parsed.char_count,
                len(parsed.sections),
                json.dumps(meta, ensure_ascii=False) if meta else None,
                PROFILE_STATUS_READY,
                now,
                now,
                doc_id,
            ),
        )
        await db.commit()
        logger.info("文档解析完成: id=%s sections=%d profile_status=ready", doc_id, len(parsed.sections))
    except Exception as exc:
        logger.exception("文档导入失败: %s", safe_name)
        await db.execute(
            "UPDATE documents SET status='error', error_message=?, profile_status=?, updated_at=? WHERE id=?",
            (str(exc), PROFILE_STATUS_ERROR, _now_iso(), doc_id),
        )
        await db.commit()
        raise
    return doc_id


async def create_document_from_text(title: str, content: str, user_id: str | None = None) -> str:
    """从文本创建知识条目（问题库「转为知识」）。写入 .md 文件后走标准导入链路。"""
    title = (title or "知识条目").strip()
    content = (content or "").strip()
    if not content:
        raise ValueError("内容不能为空")
    storage_dir = Path(settings.documents_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".md", prefix="kb_text_", dir=str(storage_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("# " + title + chr(10) + chr(10) + content + chr(10))
        with open(tmp_path, "rb") as f:
            data = f.read()
        return await import_document(f"{title}.md", data, user_id=user_id)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _save_sections(doc_id: str, parsed, now: str) -> None:
    db = get_db()
    rows = []
    for idx, s in enumerate(parsed.sections):
        rows.append(
            (
                new_id("sec_"),
                doc_id,
                idx,
                s.heading,
                s.content,
                s.page_number,
                s.parent_heading,
                s.level,
                s.char_count,
            )
        )
    await db.executemany(
        "INSERT INTO document_sections(id, document_id, section_index, heading, content, "
        "page_number, parent_heading, level, char_count) VALUES(?,?,?,?,?,?,?,?,?)",
        rows,
    )
    await db.commit()


async def _generate_profile(doc_id: str, title: str, full_text: str) -> dict:
    """生成文档画像。LLM 不可用时回退到启发式画像。"""
    content = full_text[: _PROFILE_CONTENT_MAX]
    try:
        llm = LLMClient()
        system, user = profiler_prompt.build(title, content)
        profile = await llm.structured_object(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            call_type="document_profiler",
            schema_hint="请输出符合上述要求的 JSON 对象：{title, summary, topics, entities, keywords, possible_questions}",
        )
        logger.info("画像生成(LLM): doc_id=%s", doc_id)
        return profile
    except (LLMNotConfiguredError, LLMError) as exc:
        logger.info("LLM 画像不可用，使用启发式画像（%s）", exc)
        return heuristic_profile(title, full_text)


def heuristic_profile(title: str, full_text: str) -> dict:
    counter: Counter = Counter()
    for seg in _CJK_RUN_RE.findall(full_text):
        if len(seg) >= 2:
            for i in range(len(seg) - 1):
                bg = seg[i : i + 2]
                if bg[0] not in _STOPWORDS and bg[1] not in _STOPWORDS:
                    counter[bg] += 1
    keywords = [w for w, _ in counter.most_common(20)]
    summary = " ".join(full_text.split())[:150]
    if len(full_text) > 150:
        summary += "…"
    return {
        "title": title,
        "summary": summary,
        "topics": [],
        "entities": [],
        "keywords": keywords,
        "possible_questions": [],
    }


async def _save_profile(doc_id: str, profile: dict, now: str) -> None:
    db = get_db()
    await db.execute(
        "INSERT INTO document_profiles(document_id, title, summary, topics, entities, "
        "keywords, possible_questions, profile_json, created_at) VALUES(?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(document_id) DO UPDATE SET title=EXCLUDED.title, summary=EXCLUDED.summary, "
        "topics=EXCLUDED.topics, entities=EXCLUDED.entities, keywords=EXCLUDED.keywords, "
        "possible_questions=EXCLUDED.possible_questions, profile_json=EXCLUDED.profile_json",
        (
            doc_id,
            profile.get("title", ""),
            profile.get("summary", ""),
            json.dumps(profile.get("topics", []), ensure_ascii=False),
            json.dumps(profile.get("entities", []), ensure_ascii=False),
            json.dumps(profile.get("keywords", []), ensure_ascii=False),
            json.dumps(profile.get("possible_questions", []), ensure_ascii=False),
            json.dumps(profile, ensure_ascii=False),
            now,
        ),
    )
    await db.commit()


async def _set_profile_status(doc_id: str, status: str, error: str | None = None) -> None:
    db = get_db()
    await db.execute(
        "UPDATE documents SET profile_status=?, profile_error=?, updated_at=? WHERE id=?",
        (status, error, _now_iso(), doc_id),
    )
    await db.commit()


async def get_document_profile(doc_id: str) -> dict | None:
    """读取画像（含生成状态）。文档不存在返回 None。"""
    db = get_db()
    doc = await db.execute_fetchone(
        "SELECT id, profile_status, profile_error FROM documents WHERE id=?", (doc_id,)
    )
    if doc is None:
        return None
    row = await db.execute_fetchone(
        "SELECT document_id, title, summary, topics, entities, keywords, possible_questions, "
        "profile_json, created_at FROM document_profiles WHERE document_id=?",
        (doc_id,),
    )
    profile: dict | None = None
    if row is not None:
        profile = {
            "document_id": row["document_id"],
            "title": row["title"] or "",
            "summary": row["summary"] or "",
            "topics": _json_array(row["topics"]),
            "entities": _json_array(row["entities"]),
            "keywords": _json_array(row["keywords"]),
            "possible_questions": _json_array(row["possible_questions"]),
            "created_at": row["created_at"],
        }
        if row["profile_json"]:
            try:
                profile["raw"] = json.loads(row["profile_json"])
            except json.JSONDecodeError:
                pass
    return {
        "document_id": doc_id,
        "profile_status": doc["profile_status"] or PROFILE_STATUS_NONE,
        "profile_error": doc["profile_error"],
        "profile": profile,
    }


async def generate_document_profile(doc_id: str) -> dict:
    """生成/重新生成文档画像。带状态机：generating → ready | error。"""
    db = get_db()
    doc = await db.execute_fetchone(
        "SELECT id, title, full_text, status FROM documents WHERE id=?", (doc_id,)
    )
    if doc is None:
        raise KeyError(f"文档不存在: {doc_id}")
    await _set_profile_status(doc_id, PROFILE_STATUS_GENERATING)
    logger.info("画像生成开始: doc_id=%s", doc_id)
    try:
        profile = await _generate_profile(doc_id, doc["title"] or "", doc["full_text"] or "")
        await _save_profile(doc_id, profile, _now_iso())
        await _set_profile_status(doc_id, PROFILE_STATUS_READY)
        # 画像变化会影响 fts_documents 的 keywords/entities/questions → 重建索引
        await _index_fts(doc_id)
        logger.info("画像生成完成: doc_id=%s", doc_id)
        return await get_document_profile(doc_id)
    except Exception as exc:
        logger.exception("画像生成失败: doc_id=%s", doc_id)
        await _set_profile_status(doc_id, PROFILE_STATUS_ERROR, str(exc))
        raise


async def _index_fts(doc_id: str) -> None:
    """重建该文档的 FTS 索引（先删除再插入）。"""
    db = get_db()
    await db.execute("DELETE FROM fts_documents WHERE doc_id=?", (doc_id,))
    await db.execute("DELETE FROM fts_sections WHERE doc_id=?", (doc_id,))

    doc = await db.execute_fetchone(
        "SELECT d.id, d.title, d.full_text, p.summary, p.keywords, p.entities, p.possible_questions "
        "FROM documents d LEFT JOIN document_profiles p ON p.document_id=d.id WHERE d.id=?",
        (doc_id,),
    )
    if doc is None:
        return
    title = doc["title"] or ""
    keywords = _json_array(doc["keywords"])
    entities = _json_array(doc["entities"])
    questions = _json_array(doc["possible_questions"])
    summary = doc["summary"] or ""

    kw_text = tokenize_for_fts(" ".join(keywords))
    ent_text = tokenize_for_fts(" ".join(entities))
    title_tok = tokenize_for_fts(title)
    summary_tok = tokenize_for_fts(summary)
    questions_tok = tokenize_for_fts(" ".join(questions))

    # PG：写入 search_tokens 组合串（供 pg_trgm 匹配）
    doc_tokens = " ".join(t for t in [title_tok, summary_tok, kw_text, ent_text, questions_tok] if t)
    await db.execute(
        "INSERT INTO fts_documents(doc_id, title, summary, keywords, entities, possible_questions, search_tokens) "
        "VALUES(?,?,?,?,?,?,?)",
        (doc_id, title_tok, summary_tok, kw_text, ent_text, questions_tok, doc_tokens),
    )

    rows = await db.execute_fetchall(
        "SELECT id, heading, content FROM document_sections WHERE document_id=? ORDER BY section_index",
        (doc_id,),
    )
    await db.executemany(
        "INSERT INTO fts_sections(doc_id, section_id, title, heading, content, keywords, entities, search_tokens) "
        "VALUES(?,?,?,?,?,?,?,?)",
        [
            (
                doc_id,
                r["id"],
                title_tok,
                tokenize_for_fts(r["heading"] or ""),
                tokenize_for_fts(r["content"] or ""),
                kw_text,
                ent_text,
                " ".join(
                    t
                    for t in [
                        title_tok,
                        tokenize_for_fts(r["heading"] or ""),
                        tokenize_for_fts(r["content"] or ""),
                        kw_text,
                        ent_text,
                    ]
                    if t
                ),
            )
            for r in rows
        ],
    )
    await db.commit()
    logger.info("索引已刷新: doc_id=%s sections=%d", doc_id, len(rows))


def _json_array(raw) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


async def update_document_content(
    doc_id: str, title: str | None = None, full_text: str | None = None
) -> dict:
    """在线编辑保存：更新标题/当前知识正文。

    保存后 content_version+1、sync_status='pending_reparse'（待重新解析），
    明确提示「RAG 仍使用旧索引，需重解析后才生效」。
    """
    db = get_db()
    doc = await db.execute_fetchone(
        "SELECT id, title, full_text, content_version, index_version, sync_status, edited_at, status "
        "FROM documents WHERE id=?",
        (doc_id,),
    )
    if doc is None:
        raise KeyError(f"文档不存在: {doc_id}")

    new_title = title if title is not None else doc["title"]
    new_text = full_text if full_text is not None else doc["full_text"]
    if new_title is not None:
        new_title = str(new_title).strip()
    if not new_title:
        new_title = doc["title"] or "未命名文档"

    changed = (title is not None and new_title != (doc["title"] or "")) or (
        full_text is not None and new_text != (doc["full_text"] or "")
    )
    now = _now_iso()
    if changed:
        content_version = (doc["content_version"] or 0) + 1
        await db.execute(
            "UPDATE documents SET title=?, full_text=?, char_count=?, "
            "content_version=?, sync_status='pending_reparse', edited_at=?, updated_at=? WHERE id=?",
            (new_title, new_text, len(new_text or ""), content_version, now, now, doc_id),
        )
        await db.commit()
        logger.info("文档内容已保存(待重新解析): id=%s content_version=%d", doc_id, content_version)
    return await get_document(doc_id)


async def reprocess_document(doc_id: str) -> None:
    """重新解析文档。

    流程：读取当前数据 → 解析（编辑过的文档用「当前知识正文」，否则用原始文件）
    → 删除旧章节/画像/索引 → 写新章节 → 重新画像 → 重建索引 → 状态回写。
    解析阶段先完成再清理旧数据：解析失败时旧数据保留，仅标记失败。
    """
    db = get_db()
    row = await db.execute_fetchone(
        "SELECT id, filename, storage_path, full_text, title, edited_at, content_version "
        "FROM documents WHERE id=?",
        (doc_id,),
    )
    if row is None:
        raise KeyError(f"文档不存在: {doc_id}")

    logger.info("重解析开始: doc_id=%s edited_at=%s", doc_id, row["edited_at"])

    # 1. 解析（失败则旧数据保留）；同步解析放入线程池避免阻塞事件循环
    try:
        if row["edited_at"]:
            parsed = await asyncio.to_thread(
                _parse_current_text, row["full_text"], row["title"] or row["filename"]
            )
            logger.info("重解析使用当前知识正文: doc_id=%s", doc_id)
        else:
            parsed = await asyncio.to_thread(parse_document, row["storage_path"], row["filename"])
    except Exception as exc:
        logger.exception("重解析-解析阶段失败: %s", doc_id)
        await db.execute(
            "UPDATE documents SET sync_status='failed', error_message=?, updated_at=? WHERE id=?",
            (str(exc), _now_iso(), doc_id),
        )
        await db.commit()
        raise

    # 2. 清理旧数据
    await db.execute("DELETE FROM document_sections WHERE document_id=?", (doc_id,))
    await db.execute("DELETE FROM document_profiles WHERE document_id=?", (doc_id,))
    await db.execute("DELETE FROM fts_documents WHERE doc_id=?", (doc_id,))
    await db.execute("DELETE FROM fts_sections WHERE doc_id=?", (doc_id,))
    await db.execute(
        "UPDATE documents SET status='processing', sync_status='reparsing', "
        "profile_status=?, profile_error=NULL, error_message=NULL, updated_at=? WHERE id=?",
        (PROFILE_STATUS_GENERATING, _now_iso(), doc_id),
    )
    await db.commit()

    try:
        now = _now_iso()
        await _save_sections(doc_id, parsed, now)
        profile = await _generate_profile(doc_id, parsed.title, parsed.full_text)
        await _save_profile(doc_id, profile, now)
        await _index_fts(doc_id)
        # 编辑过的文档保持编辑后的标题/正文（不覆盖）
        final_title = (row["title"] or "") if row["edited_at"] else parsed.title
        final_text = (row["full_text"] or "") if row["edited_at"] else parsed.full_text
        content_version = row["content_version"] or 1
        await db.execute(
            "UPDATE documents SET title=?, full_text=?, char_count=?, section_count=?, "
            "status='ready', sync_status='synced', profile_status=?, profile_error=NULL, "
            "index_version=?, last_parsed_at=?, updated_at=? WHERE id=?",
            (
                final_title,
                final_text,
                len(final_text or ""),
                len(parsed.sections),
                PROFILE_STATUS_READY,
                content_version,
                now,
                now,
                doc_id,
            ),
        )
        await db.commit()
        logger.info(
            "重解析完成: doc_id=%s sections=%d content_version=%d index_version=%d",
            doc_id,
            len(parsed.sections),
            content_version,
            content_version,
        )
    except Exception as exc:
        logger.exception("文档重新解析失败: %s", doc_id)
        await db.execute(
            "UPDATE documents SET status='error', sync_status='failed', error_message=?, "
            "profile_status=?, updated_at=? WHERE id=?",
            (str(exc), PROFILE_STATUS_ERROR, _now_iso(), doc_id),
        )
        await db.commit()
        raise


async def delete_document(doc_id: str) -> None:
    db = get_db()
    row = await db.execute_fetchone("SELECT storage_path FROM documents WHERE id=?", (doc_id,))
    if row is None:
        return
    await db.execute("DELETE FROM fts_documents WHERE doc_id=?", (doc_id,))
    await db.execute("DELETE FROM fts_sections WHERE doc_id=?", (doc_id,))
    await db.execute("DELETE FROM documents WHERE id=?", (doc_id,))  # 级联删除 sections/profiles
    await db.commit()
    try:
        Path(row["storage_path"]).unlink(missing_ok=True)
    except OSError:
        pass
    logger.info("文档已删除: doc_id=%s", doc_id)


async def set_document_status(doc_id: str, status: str) -> None:
    db = get_db()
    await db.execute(
        "UPDATE documents SET status=?, updated_at=? WHERE id=?",
        (status, _now_iso(), doc_id),
    )
    await db.commit()


async def list_documents() -> list[dict]:
    db = get_db()
    rows = await db.execute_fetchall(
        "SELECT d.id, d.filename, d.title, d.file_type, d.created_at, d.updated_at, d.status, "
        "d.error_message, d.char_count, d.section_count, d.last_parsed_at, "
        "d.content_version, d.index_version, d.sync_status, d.profile_status, d.profile_error, "
        "d.edited_at, p.summary, "
        "COALESCE(u.username, '') AS uploader "
        "FROM documents d LEFT JOIN document_profiles p ON p.document_id=d.id "
        "LEFT JOIN users u ON u.id=d.user_id "
        "ORDER BY d.created_at DESC"
    )
    return [dict(r) for r in rows]


async def get_document(doc_id: str) -> dict | None:
    db = get_db()
    row = await db.execute_fetchone(
        "SELECT d.*, p.profile_json FROM documents d "
        "LEFT JOIN document_profiles p ON p.document_id=d.id WHERE d.id=?",
        (doc_id,),
    )
    if row is None:
        return None
    data = dict(row)
    if data.get("profile_json"):
        try:
            data["profile"] = json.loads(data["profile_json"])
        except json.JSONDecodeError:
            data["profile"] = None
    else:
        data["profile"] = None
    data.pop("profile_json", None)
    return data


async def get_document_sections(doc_id: str) -> list[dict]:
    db = get_db()
    rows = await db.execute_fetchall(
        "SELECT id, section_index, heading, content, page_number, parent_heading, level, char_count "
        "FROM document_sections WHERE document_id=? ORDER BY section_index",
        (doc_id,),
    )
    return [dict(r) for r in rows]


async def count_ready_documents() -> int:
    db = get_db()
    row = await db.execute_fetchone(
        "SELECT COUNT(*) AS c FROM documents WHERE status='ready'"
    )
    return row["c"] if row else 0
