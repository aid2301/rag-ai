"""全文检索（PostgreSQL pg_trgm）。

对 bigram 分词后的 token 列用 `word_similarity(查询串, search_tokens)` 匹配
（查询串在前），按相似度降序返回。查询与索引使用同一套分词（utils.text）。
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.database import get_db
from app.utils.text import tokenize_for_fts

MAX_SECTIONS = 50
logger = get_logger(__name__)


async def search_sections(keywords: list[str], limit: int = MAX_SECTIONS) -> list[dict]:
    """按关键词检索章节，返回按相关性排序的 (section_id, doc_id, rank)。"""
    tokens = _query_tokens(keywords)
    if not tokens:
        return []
    db = get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT f.section_id, f.doc_id, word_similarity(?, f.search_tokens) AS rank "
            "FROM fts_sections f JOIN documents d ON d.id=f.doc_id "
            "WHERE d.status='ready' AND word_similarity(?, f.search_tokens) > 0.3 "
            "ORDER BY rank DESC LIMIT ?",
            (tokens, tokens, limit),
        )
    except Exception as exc:
        logger.warning("章节全文检索失败: %s", exc)
        return []
    return [dict(r) for r in rows]


async def search_documents(keywords: list[str], limit: int = 20) -> list[dict]:
    """按关键词检索文档级索引（画像+标题）。"""
    tokens = _query_tokens(keywords)
    if not tokens:
        return []
    db = get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT f.doc_id, word_similarity(?, f.search_tokens) AS rank "
            "FROM fts_documents f JOIN documents d ON d.id=f.doc_id "
            "WHERE d.status='ready' AND word_similarity(?, f.search_tokens) > 0.3 "
            "ORDER BY rank DESC LIMIT ?",
            (tokens, tokens, limit),
        )
    except Exception as exc:
        logger.warning("文档全文检索失败: %s", exc)
        return []
    return [dict(r) for r in rows]


def _query_tokens(keywords: list[str]) -> str:
    """把关键词列表合并为与索引一致的 token 串。"""
    parts = [kw for kw in keywords if kw and kw.strip()]
    if not parts:
        return ""
    return tokenize_for_fts(" ".join(parts))
