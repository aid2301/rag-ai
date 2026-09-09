"""Context Builder：构建送入 LLM 的证据上下文。

策略：
- 小文档（<= full_document_max_chars）→ Full Document Mode，整篇进入上下文
- 大文档 → Section Retrieval Mode，取重排后的章节 + 邻接章节扩展
- 总长度受 context_budget_chars 约束
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import get_db

logger = get_logger(__name__)


@dataclass
class Citation:
    index: int
    document_id: str
    document_title: str
    section: str
    page: int | None = None


@dataclass
class ContextResult:
    text: str
    citations: list[Citation] = field(default_factory=list)
    used_chars: int = 0
    truncated: bool = False


class ContextBuilder:
    def __init__(self) -> None:
        self.max_chars = settings.context_budget_chars
        self.full_doc_max = settings.full_document_max_chars
        self.neighbor_radius = settings.neighbor_radius

    async def build(
        self,
        selected_docs: list[dict],
        candidate_sections: list[dict],
        *,
        expand_neighbors: bool,
    ) -> ContextResult:
        """selected_docs: [{document_id, title, char_count, full_text}]
        candidate_sections: [{section_id, document_id, heading, content, page_number,
                              parent_heading, section_index, score, reason}]
        """
        blocks: list[dict] = []
        used = 0
        truncated = False

        for doc in selected_docs:
            if used >= self.max_chars:
                truncated = True
                break
            doc_sections = [
                s for s in candidate_sections if s.get("document_id") == doc["document_id"]
            ]
            if doc.get("char_count", 0) <= self.full_doc_max:
                block = self._full_doc_block(doc)
            else:
                block = await self._section_block(doc, doc_sections, expand_neighbors)
            if block is None:
                continue

            content = block["content"]
            remaining = self.max_chars - used
            if len(content) > remaining:
                content = content[:remaining]
                truncated = True
            block["content"] = content
            block["index"] = len(blocks) + 1
            blocks.append(block)
            used += len(content)

        citations = [
            Citation(
                index=b["index"],
                document_id=b["document_id"],
                document_title=b["document_title"],
                section=b["section"],
                page=b["page"],
            )
            for b in blocks
        ]
        text = "\n\n---\n\n".join(self._render(b) for b in blocks)
        return ContextResult(text=text, citations=citations, used_chars=used, truncated=truncated)

    # ---------- 内部 ----------

    def _full_doc_block(self, doc: dict) -> dict | None:
        text = (doc.get("full_text") or "").strip()
        if not text:
            return None
        return {
            "document_id": doc["document_id"],
            "document_title": doc.get("title") or "",
            "section": "全文",
            "page": None,
            "content": text,
            "metadata": doc.get("metadata"),
        }

    async def _section_block(
        self, doc: dict, sections: list[dict], expand: bool
    ) -> dict | None:
        if not sections:
            return None
        # 按分数排序取前 N 个主命中章节
        ordered = sorted(
            sections, key=lambda s: s.get("score", 0) or 0, reverse=True
        )
        main = ordered[: settings.top_sections_after_rerank]

        selected_ids = {s["section_id"] for s in main}
        if expand:
            expanded = await self._expand_neighbors(doc["document_id"], selected_ids)
        else:
            expanded = self._load_by_ids(main)

        if not expanded:
            return None

        parts: list[str] = []
        first_heading = ""
        first_page: int | None = None
        for sec in expanded:
            content = (sec.get("content") or "").strip()
            if not content:
                continue
            heading = sec.get("heading") or "（无标题）"
            if not first_heading:
                first_heading = heading
            if first_page is None:
                first_page = sec.get("page_number")
            page_note = f"（第 {sec['page_number']} 页）" if sec.get("page_number") else ""
            parts.append(f"【{heading}】{page_note}\n{content}")
        content = "\n\n".join(p for p in parts if p)
        if not content:
            return None
        return {
            "document_id": doc["document_id"],
            "document_title": doc.get("title") or "",
            "section": first_heading,
            "page": first_page,
            "content": content,
            "metadata": doc.get("metadata"),
        }

    async def _expand_neighbors(
        self, doc_id: str, selected_ids: set[str]
    ) -> list[dict]:
        """邻接章节扩展：命中章节的前后 radius 个章节 + 同父章节。"""
        db = get_db()
        rows = await db.execute_fetchall(
            "SELECT id, section_index, heading, content, page_number, parent_heading "
            "FROM document_sections WHERE document_id=? ORDER BY section_index",
            (doc_id,),
        )
        all_secs = [dict(r) for r in rows]
        by_id = {s["id"]: s for s in all_secs}
        target: set[int] = set()
        for sid in selected_ids:
            sec = by_id.get(sid)
            if sec is None:
                continue
            idx = sec["section_index"]
            parent = sec.get("parent_heading")
            for i in range(
                max(0, idx - self.neighbor_radius),
                min(len(all_secs), idx + self.neighbor_radius + 1),
            ):
                target.add(i)
            # 同父章节（父章节下的所有子章节）
            if parent:
                for i, s in enumerate(all_secs):
                    if s.get("parent_heading") == parent:
                        target.add(i)
        ordered = [all_secs[i] for i in sorted(target)]
        return ordered

    def _load_by_ids(self, sections: list[dict]) -> list[dict]:
        # 不扩展时保持传入顺序（已按相关性排序）
        return sections

    def _render(self, block: dict) -> str:
        lines = [
            f"[SOURCE {block['index']}]",
            f"Document: {block['document_title'] or '（未命名文档）'}",
            f"Section: {block['section']}",
        ]
        if block.get("page"):
            lines.append(f"Page: {block['page']}")
        meta = block.get("metadata")
        if meta:
            parts = []
            if meta.get("version"):
                parts.append(f"版本: {meta['version']}")
            if meta.get("effective_date"):
                parts.append(f"生效日期: {meta['effective_date']}")
            if meta.get("status"):
                parts.append(f"状态: {meta['status']}")
            if parts:
                lines.append("元数据: " + "；".join(parts))
        lines.append("Content:")
        lines.append(block["content"])
        return "\n".join(lines)
