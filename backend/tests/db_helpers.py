"""Database fixtures live here, never in the production application.

TEST_DATABASE_URL must name a disposable database ending in _test.
"""
from __future__ import annotations

import os
from urllib.parse import unquote, urlsplit

import asyncpg

from app.db import database


def test_database_url() -> str:
    dsn = os.environ.get("TEST_DATABASE_URL", "postgresql://kb:kb@127.0.0.1:55433/kb_test")
    name = unquote(urlsplit(dsn).path.lstrip("/"))
    if not name.endswith("_test"):
        raise ValueError("TEST_DATABASE_URL must target a disposable database ending in _test")
    return dsn


async def init_db_for_test():
    await database.close_db()
    dsn = test_database_url()
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("DROP SCHEMA public CASCADE")
        await conn.execute("CREATE SCHEMA public")
    finally:
        await conn.close()
    database._pool = await database._init_pool(dsn)
    database._db = database.PooledConn(database._pool)
    return database._db
