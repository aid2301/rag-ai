"""Idempotent schema upgrades shared by application startup and tests."""

# 幂等迁移：每次启动执行（ADD COLUMN IF NOT EXISTS / UPDATE 回填）。
# 新表在 SCHEMA_PG 中声明；对已存在表的新增列在此声明。
MIGRATIONS: list[str] = [
    # ---- documents：版本追踪 / 解析状态 / 画像状态 / 编辑标记 ----
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS last_parsed_at TEXT",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_version INTEGER DEFAULT 0",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS index_version INTEGER DEFAULT 0",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS sync_status TEXT DEFAULT 'synced'",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS profile_status TEXT DEFAULT 'none'",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS profile_error TEXT",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS edited_at TEXT",
    # ---- messages：回答状态 ----
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS answer_status TEXT DEFAULT 'answered'",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS insufficient_reason TEXT",
    # ---- questions：回答有误反馈 + 上下文快照（M1） ----
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS feedback_type TEXT DEFAULT 'insufficient'",
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS feedback_note TEXT",
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual'",
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS context_snapshot TEXT",
    # ---- questions：自动分组建议（M2） ----
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS suggested_group_id TEXT",
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS suggested_reason TEXT",
    # ---- 回填：已 ready 文档视为「已解析 + 已同步 + 已有画像」 ----
    "UPDATE documents SET content_version=1, index_version=1, sync_status='synced', "
    "last_parsed_at=COALESCE(updated_at, created_at) "
    "WHERE status='ready' AND content_version=0",
    "UPDATE documents SET profile_status='ready' "
    "WHERE profile_status='none' AND EXISTS "
    "(SELECT 1 FROM document_profiles p WHERE p.document_id=documents.id)",
]
