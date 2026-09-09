"""PostgreSQL Schema。

与 `schema.py`（SQLite）保持表结构对齐。差异：
- ID 主键：`TEXT`（业务层 UUID 字符串），保持跨库一致
- token_usage.id：`GENERATED ALWAYS AS IDENTITY`（替代 SQLite AUTOINCREMENT）
- 全文检索：不再使用 SQLite FTS5 虚拟表，改为对「已 bigram 分词」的 token 列
  建 pg_trgm GIN 索引，检索用 `%`（similarity）匹配，保持中文检索语义
"""
from __future__ import annotations

SCHEMA_PG = """
-- pg_trgm 扩展：trigram 相似度检索（必须在建索引前启用）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT,
    is_active     INTEGER DEFAULT 1,
    created_at    TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    filename      TEXT NOT NULL,
    title         TEXT,
    file_type     TEXT,
    storage_path  TEXT,
    full_text     TEXT,
    char_count    INTEGER DEFAULT 0,
    section_count INTEGER DEFAULT 0,
    status        TEXT DEFAULT 'processing',
    error_message TEXT,
    metadata      TEXT,
    user_id       TEXT,
    created_at    TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS document_sections (
    id             TEXT PRIMARY KEY,
    document_id    TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section_index  INTEGER,
    heading        TEXT,
    content        TEXT,
    page_number    INTEGER,
    parent_heading TEXT,
    level          INTEGER DEFAULT 1,
    char_count     INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sections_doc ON document_sections(document_id, section_index);

CREATE TABLE IF NOT EXISTS document_profiles (
    document_id       TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    title             TEXT,
    summary           TEXT,
    topics            TEXT,
    entities          TEXT,
    keywords          TEXT,
    possible_questions TEXT,
    profile_json      TEXT,
    created_at        TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT PRIMARY KEY,
    title      TEXT,
    summary    TEXT,
    user_id    TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT,
    citations       TEXT,
    debug_info      TEXT,
    token_usage     TEXT,
    created_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS token_usage (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    call_type         TEXT,
    model             TEXT,
    user_id           TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    latency_ms        DOUBLE PRECISION,
    created_at        TEXT
);

-- 文档级检索：已是 bigram 分词后的 token 串，用 trigram 相似度匹配
CREATE TABLE IF NOT EXISTS fts_documents (
    doc_id             TEXT PRIMARY KEY,
    title              TEXT,
    summary            TEXT,
    keywords           TEXT,
    entities           TEXT,
    possible_questions TEXT,
    -- 组合分词列的 trigram GIN 索引（供 `%` 匹配）
    search_tokens      TEXT
);
CREATE INDEX IF NOT EXISTS idx_fts_documents_trgm ON fts_documents USING GIN (search_tokens gin_trgm_ops);

-- 章节级检索
CREATE TABLE IF NOT EXISTS fts_sections (
    doc_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section_id TEXT PRIMARY KEY,
    title      TEXT,
    heading    TEXT,
    content    TEXT,
    keywords   TEXT,
    entities   TEXT,
    search_tokens TEXT
);
CREATE INDEX IF NOT EXISTS idx_fts_sections_trgm ON fts_sections USING GIN (search_tokens gin_trgm_ops);

-- 问题库：知识缺口管理
CREATE TABLE IF NOT EXISTS question_groups (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS questions (
    id                    TEXT PRIMARY KEY,
    question              TEXT NOT NULL,
    original_questions    TEXT,
    occurrence_count      INTEGER DEFAULT 1,
    status                TEXT DEFAULT 'pending',
    group_id              TEXT REFERENCES question_groups(id) ON DELETE SET NULL,
    user_id               TEXT,
    source_conversation_id TEXT,
    source_message_id     TEXT,
    ai_answer             TEXT,
    answer_status         TEXT,
    retrieval_snapshot    TEXT,
    model                 TEXT,
    standard_answer       TEXT,
    assignee              TEXT,
    -- M1 优化：回答有误反馈 + 上下文快照
    feedback_type         TEXT DEFAULT 'insufficient',
    feedback_note         TEXT,
    source                TEXT DEFAULT 'manual',
    context_snapshot      TEXT,
    -- M2：LLM 自动分组建议
    suggested_group_id    TEXT,
    suggested_reason      TEXT,
    created_at            TEXT,
    updated_at            TEXT,
    processed_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
CREATE INDEX IF NOT EXISTS idx_questions_group ON questions(group_id);
CREATE INDEX IF NOT EXISTS idx_questions_msg ON questions(source_message_id);
"""