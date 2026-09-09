"""文档管理 API（仅管理员可访问）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field

from app.core.admin import require_admin
from app.core.config import settings
from app.services import documents
from app.services.document_parser import SUPPORTED_EXTENSIONS

router = APIRouter(prefix="/api/documents", tags=["documents"], dependencies=[Depends(require_admin)])


class DocumentEditBody(BaseModel):
    """在线编辑：title / full_text 至少一个；status 仅 ready|disabled。"""
    status: str | None = None
    title: str | None = None
    full_text: str | None = None


class TextDocumentBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(..., min_length=1)


@router.post("")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
):
    ext = ("." + (file.filename or "").rsplit(".", 1)[-1].lower()) if "." in (file.filename or "") else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {ext or '未知'}。支持: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    # 大小限制：优先用 Content-Length 提前拒绝；读入时再兜底（避免整文件读内存超限）
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    try:
        content_length = int(request.headers.get("content-length") or 0)
    except (TypeError, ValueError):
        content_length = 0
    if content_length > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{content_length} 字节），超过上限 {settings.max_upload_size_mb}MB",
        )

    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，超过上限 {settings.max_upload_size_mb}MB",
        )
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    try:
        doc_id = await documents.import_document(file.filename or "unnamed", content, user_id=None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文档导入失败: {exc}")
    return {"document_id": doc_id}


@router.post("/text")
async def create_text_document(body: TextDocumentBody):
    """从文本创建知识条目（问题库「转为知识」等场景）。"""
    # M1-Q03：拒绝「无法回答」固定文案，防止生成污染知识库的垃圾条目
    from app.services.rag.steps import INSUFFICIENT_ANSWER

    if (body.content or "").strip() == INSUFFICIENT_ANSWER:
        raise HTTPException(status_code=400, detail="请先填写标准答案再转为知识条目")
    try:
        doc_id = await documents.create_document_from_text(body.title, body.content, user_id=None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"知识条目创建失败: {exc}")
    return {"document_id": doc_id}


@router.get("")
async def list_documents():
    return await documents.list_documents()


@router.get("/{doc_id}")
async def get_document(doc_id: str):
    doc = await documents.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


@router.get("/{doc_id}/raw")
async def get_document_raw(doc_id: str):
    doc = await documents.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"document_id": doc_id, "filename": doc["filename"], "title": doc.get("title"), "full_text": doc.get("full_text") or ""}


@router.get("/{doc_id}/sections")
async def get_document_sections(doc_id: str):
    doc = await documents.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return await documents.get_document_sections(doc_id)


# ---------- 画像 ----------

@router.get("/{doc_id}/profile")
async def get_document_profile(doc_id: str):
    """读取文档画像（含生成状态：none/generating/ready/error）。"""
    profile = await documents.get_document_profile(doc_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return profile


@router.post("/{doc_id}/profile")
async def generate_document_profile(doc_id: str):
    """生成/重新生成文档画像（LLM 调用，返回最终画像与状态）。"""
    try:
        return await documents.generate_document_profile(doc_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"画像生成失败: {exc}")


# ---------- 重解析 ----------

@router.post("/{doc_id}/reprocess")
@router.post("/{doc_id}/reparse")
async def reprocess_document(doc_id: str):
    """重新解析文档（/reprocess 与 /reparse 均可用，前端历史兼容）。"""
    try:
        await documents.reprocess_document(doc_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"重新解析失败: {exc}")
    return {"ok": True}


# ---------- 状态 / 编辑 ----------

@router.patch("/{doc_id}/status")
@router.patch("/{doc_id}")
async def update_document(doc_id: str, body: DocumentEditBody):
    """文档更新：
    - status: ready|disabled（停用/启用）
    - title / full_text: 在线编辑保存（content_version+1，sync_status=pending_reparse）
    """
    doc = await documents.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if body.status is not None:
        if body.status not in ("ready", "disabled"):
            raise HTTPException(status_code=400, detail="status 必须是 ready 或 disabled")
        await documents.set_document_status(doc_id, body.status)
        return await documents.get_document(doc_id)
    try:
        return await documents.update_document_content(
            doc_id, title=body.title, full_text=body.full_text
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存失败: {exc}")


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    await documents.delete_document(doc_id)
    return {"ok": True}
