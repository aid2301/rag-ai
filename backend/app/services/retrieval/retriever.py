"""候选文档召回：精确匹配 + FTS5/BM25 + 文档画像。"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.db.database import get_db
from app.services.retrieval import fts

logger = get_logger(__name__)

_MAX_CANDIDATE_SECTIONS = 40
MAX_FTS_SECTIONS = 40


@dataclass
class CandidateDocument:
    document_id: str
    title: str
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class RetrievedSection:
    section_id: str
    document_id: str
    heading: str
    content: str
    page_number: int | None
    parent_heading: str | None
    score: float
    reason: str = ""
    document_title: str = ""


@dataclass
class RetrievalResult:
    candidates: list[CandidateDocument] = field(default_factory=list)
    sections: list[RetrievedSection] = field(default_factory=list)


def _collect_keywords(query_plan: dict) -> list[str]:
    keywords: list[str] = []
    for key in ("keywords", "entities"):
        for kw in query_plan.get(key) or []:
            if kw and str(kw).strip():
                keywords.append(str(kw).strip())
    sq = query_plan.get("standalone_query") or ""
    if sq:
        keywords.append(sq)
    # 去重保序
    seen: set[str] = set()
    result = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)
    return result


class Retriever:
    """混合非向量召回。"""

    async def retrieve(self, query_plan: dict) -> RetrievalResult:
        db = get_db()
        keywords = _collect_keywords(query_plan)
        result = RetrievalResult()

        if not keywords:
            return result

        doc_scores: dict[str, CandidateDocument] = {}
        section_scores: dict[str, RetrievedSection] = {}

        # ---------- 1. 精确匹配（权重最高） ----------
        await self._exact_match(db, keywords, doc_scores, section_scores)

        # ---------- 2. FTS5 / BM25 章节检索 ----------
        fts_rows = await fts.search_sections(keywords, limit=MAX_FTS_SECTIONS)
        for r in fts_rows:
            sec = await self._load_section(db, r["section_id"])
            if sec is None:
                continue
            similarity = max(0.0, min(1.0, float(r["rank"])))
            score = 5.0 * similarity
            if sec.section_id not in section_scores:
                section_scores[sec.section_id] = sec
            section_scores[sec.section_id].score += score
            self._bump_doc(
                doc_scores,
                sec.document_id,
                sec.document_title,
                score,
                "全文检索命中",
            )

        # ---------- 3. 文档画像检索 ----------
        fts_docs = await fts.search_documents(keywords, limit=15)
        for r in fts_docs:
            row = await db.execute_fetchone(
                "SELECT title FROM documents WHERE id=? AND status='ready'", (r["doc_id"],)
            )
            if row is None:
                continue
            similarity = max(0.0, min(1.0, float(r["rank"])))
            score = 4.0 * similarity
            self._bump_doc(doc_scores, r["doc_id"], row["title"], score, "文档画像命中")

        result.candidates = sorted(
            doc_scores.values(), key=lambda d: d.score, reverse=True
        )
        result.sections = sorted(
            section_scores.values(), key=lambda s: s.score, reverse=True
        )[: _MAX_CANDIDATE_SECTIONS]
        return result

    # ---------- 内部方法 ----------

    async def _exact_match(self, db, keywords, doc_scores, section_scores) -> None:
        """精确匹配：标题 / 章节标题 / 原文包含（实体、编号、政策名）。"""
        like_op = "ILIKE ?"
        for kw in keywords:
            if len(kw) < 2:
                continue
            # 标题精确/包含
            rows = await db.execute_fetchall(
                f"SELECT id, title FROM documents WHERE title {like_op} AND status='ready'",
                (f"%{kw}%",),
            )
            for r in rows:
                self._bump_doc(doc_scores, r["id"], r["title"], 10.0, f"标题精确匹配「{kw}」")

            # 章节标题匹配
            rows = await db.execute_fetchall(
                f"SELECT s.id, s.document_id, s.heading, d.title AS document_title "
                f"FROM document_sections s JOIN documents d ON d.id=s.document_id "
                f"WHERE d.status='ready' AND s.heading {like_op}",
                (f"%{kw}%",),
            )
            for r in rows:
                self._bump_doc(
                    doc_scores,
                    r["document_id"],
                    r["document_title"],
                    8.0,
                    f"章节标题匹配「{kw}」",
                )

            # 原文包含（对短编号/代码类关键词权重更高）
            weight = 6.0
            if any(ch.isdigit() for ch in kw):
                weight = 9.0
            rows = await db.execute_fetchall(
                f"SELECT s.id, s.document_id, s.heading, s.content, s.page_number, "
                f"s.parent_heading, s.level, d.title AS document_title "
                f"FROM document_sections s JOIN documents d ON d.id=s.document_id "
                f"WHERE d.status='ready' AND s.content {like_op} LIMIT 30",
                (f"%{kw}%",),
            )
            for r in rows:
                self._bump_doc(
                    doc_scores,
                    r["document_id"],
                    r["document_title"],
                    weight,
                    f"原文匹配「{kw}」",
                )
                sec = RetrievedSection(
                    section_id=r["id"],
                    document_id=r["document_id"],
                    heading=r["heading"],
                    content=r["content"],
                    page_number=r["page_number"],
                    parent_heading=r["parent_heading"],
                    score=weight,
                    reason=f"原文包含「{kw}」",
                    document_title=r["document_title"],
                )
                if sec.section_id not in section_scores:
                    section_scores[sec.section_id] = sec
                else:
                    section_scores[sec.section_id].score += weight

    def _bump_doc(
        self, doc_scores: dict, doc_id: str, title: str, score: float, reason: str
    ) -> None:
        doc = doc_scores.get(doc_id)
        if doc is None:
            doc = CandidateDocument(document_id=doc_id, title=title or "", score=0.0)
            doc_scores[doc_id] = doc
        doc.score += score
        if reason not in doc.reasons:
            doc.reasons.append(reason)

    async def _load_section(self, db, section_id: str) -> RetrievedSection | None:
        row = await db.execute_fetchone(
            "SELECT s.id, s.document_id, s.heading, s.content, s.page_number, "
            "s.parent_heading, s.level, d.title AS document_title "
            "FROM document_sections s JOIN documents d ON d.id=s.document_id "
            "WHERE s.id=? AND d.status='ready'",
            (section_id,),
        )
        if row is None:
            return None
        return RetrievedSection(
            section_id=row["id"],
            document_id=row["document_id"],
            heading=row["heading"],
            content=row["content"],
            page_number=row["page_number"],
            parent_heading=row["parent_heading"],
            score=0.0,
            document_title=row["document_title"],
        )
