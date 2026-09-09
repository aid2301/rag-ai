"""FastAPI 应用入口。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, admin_users, auth, chat, conversations, documents, questions, settings, usage
from app.core.config import BASE_DIR, settings as app_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.db.database import close_db, init_db

FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="企业知识库问答系统",
    description="小规模文档、高智能、非向量化 RAG 知识库",
    version="1.0.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

_origins = [o.strip() for o in app_settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(usage.router)
app.include_router(admin.router)
app.include_router(admin_users.router)
app.include_router(questions.router)
app.include_router(questions.groups_router)
app.include_router(questions.overview_router)


@app.get("/api/health")
async def health():
    """健康检查：返回服务与数据库状态。"""
    from app.db.database import get_db

    db = get_db()
    driver = "postgres"
    try:
        doc_count_row = await db.execute_fetchone("SELECT COUNT(*) AS c FROM fts_documents")
        section_count_row = await db.execute_fetchone("SELECT COUNT(*) AS c FROM fts_sections")
        return {
            "status": "ok",
            "app": "enterprise-kb",
            "database": {"driver": driver, "connected": True},
            "fts": {
                "documents": doc_count_row["c"] if doc_count_row else 0,
                "sections": section_count_row["c"] if section_count_row else 0,
            },
        }
    except Exception:
        return {
            "status": "degraded",
            "app": "enterprise-kb",
            "database": {"driver": driver, "connected": False},
            "fts": {"documents": -1, "sections": -1},
        }


# ---------- 前端静态资源（生产模式：React build 后由 FastAPI 托管） ----------
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path and full_path.startswith("api/"):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not Found")
        target = (FRONTEND_DIST / full_path).resolve()
        if not target.is_relative_to(FRONTEND_DIST.resolve()):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not Found")
        if full_path and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
