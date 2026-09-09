"""应用配置。

- 静态配置（路径、端口、RAG 参数）从环境变量 / .env 读取。
- 可变的 LLM 配置通过 SettingsStore 持久化到数据库，此处仅提供默认值。
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录：backend/app/core/config.py -> core -> app -> backend -> 项目根
BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(BASE_DIR / ".env"),
            str(BASE_DIR / "backend" / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- LLM 默认值（可被数据库 settings 表覆盖） ----
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout: float = 60.0
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048

    # 默认回答模式：auto(按复杂度自动) / fast / standard / deep
    default_chat_mode: str = "auto"
    # 是否在用户端展示思考过程（阶段进度 + 执行详情，不消耗额外 token）
    show_thinking: bool = False

    # ---- RAG 参数 ----
    # 小于该字数的文档走 Full Context 模式
    full_document_max_chars: int = 12000
    # 最终送入 LLM 的证据总字数上限
    context_budget_chars: int = 28000
    # 单个章节超过该字数允许进一步切分
    section_max_chars: int = 4000
    # 最多选择的文档数
    max_selected_documents: int = 5
    # 重排前的候选章节数
    max_rerank_sections: int = 20
    # 重排后保留的章节数
    top_sections_after_rerank: int = 8
    # 邻接章节扩展半径
    neighbor_radius: int = 1

    # ---- 文档上传 ----
    # 单文件上传大小上限（MB），超过返回 HTTP 413
    max_upload_size_mb: int = 50

    # ---- 路径 ----
    data_dir: str = str(DATA_DIR)
    documents_dir: str = str(DATA_DIR / "documents")
    database_path: str = str(DATA_DIR / "database" / "kb.db")

    # ---- 数据库（PostgreSQL 为唯一驱动） ----
    db_driver: str = "postgres"
    # PostgreSQL DSN（此为空时由下面 pg_* 拼装）
    database_url: str = ""
    pg_host: str = "127.0.0.1"
    # Docker 容器映射到宿主机的端口（容器内为 5432）
    pg_port: int = 55432
    pg_user: str = "kb"
    pg_password: str = "kb"
    pg_database: str = "kb"

    # Read SECRET_KEY from the environment or .env, like all other settings.
    secret_key: str = ""

    # ---- 管理后台 ----
    # 管理员密码（默认 admin123，强烈建议通过环境变量覆盖）
    admin_password: str = ""

    # ---- 服务 ----
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"
    # 开发模式下返回 debug 跟踪信息
    debug: bool = False


settings = Settings()