"""数据库连接管理（PostgreSQL，asyncpg 连接池）。

项目统一使用 PostgreSQL（Docker 运行）。业务代码通过 `get_db()` 拿到
统一的 `BaseConn` 接口，不直接接触驱动。

并发模型：`init_db()` 创建 asyncpg 连接池；`get_db()` 返回一个
`PooledConn` 包装对象，每次方法调用从池中 acquire 一个连接、用完立即归还。
因此任意数量的并发请求可安全共享同一个 `PooledConn`（无共享可变状态），
不会出现 asyncpg 单连接同一时刻多个 in-flight 查询导致的 InterfaceError。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

import asyncpg

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import BaseConn
from app.db.pg_conn import PGConn
from app.db.schema_pg import SCHEMA_PG

logger = get_logger(__name__)

from app.db.migrations import MIGRATIONS

# 连接池参数
_POOL_MIN_SIZE = 1
_POOL_MAX_SIZE = 10

_pool: asyncpg.Pool | None = None
_db: BaseConn | None = None


class PooledConn(BaseConn):
    """连接池包装：每次方法调用从池中获取连接，用完归还。

    业务代码仍以 `db = get_db()` 拿到本对象，无需感知池化。
    并发安全：本对象无共享可变状态，方法内部一次性占用池连接，
    asyncpg 池会按需创建连接（上限 max_size），超出时请求排队等待，
    不会产生 InterfaceError。
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        super().__init__(driver="postgres")
        self._pool = pool

    async def _run(self, fn, *args):
        """acquire 一个池连接，执行 fn(pg_conn, *args)，finally 归还。"""
        conn = await self._pool.acquire()
        pg = PGConn(conn)
        try:
            return await fn(pg, *args)
        finally:
            await self._pool.release(conn)

    async def execute(self, sql: str, parameters: Sequence[Any] = ()) -> Any:
        return await self._run(
            lambda pg, sql, parameters: pg.execute(sql, parameters), sql, parameters
        )

    async def execute_fetchall(self, sql: str, parameters: Sequence[Any] = ()) -> list[dict]:
        return await self._run(
            lambda pg, sql, parameters: pg.execute_fetchall(sql, parameters),
            sql,
            parameters,
        )

    async def execute_fetchone(self, sql: str, parameters: Sequence[Any] = ()) -> dict | None:
        return await self._run(
            lambda pg, sql, parameters: pg.execute_fetchone(sql, parameters),
            sql,
            parameters,
        )

    async def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> Any:
        return await self._run(
            lambda pg, sql, seq: pg.executemany(sql, seq), sql, seq_of_params
        )

    async def commit(self) -> None:
        # asyncpg 连接为 autocommit；显式 commit 为空操作
        return None

    async def close(self) -> None:
        # 池的关闭由 close_db 统一处理；单个包装对象不单独关闭连接
        return None


def current_driver() -> str:
    """当前数据库驱动（始终为 postgres）。"""
    return "postgres"


def database_path() -> Path:
    return Path(settings.database_path)


def _resolve_dsn(database: str | None = None) -> str:
    """解析 PostgreSQL 连接串：优先 DATABASE_URL，否则由 pg_* 拼装。"""
    dbname = database or settings.pg_database
    if settings.database_url and not database:
        return settings.database_url
    return (
        f"postgresql://{quote(settings.pg_user, safe='')}:{quote(settings.pg_password, safe='')}"
        f"@{settings.pg_host}:{settings.pg_port}/{quote(dbname, safe='')}"
    )


async def _init_pool(dsn: str | None = None) -> asyncpg.Pool:
    """创建连接池并幂等执行建表/迁移（使用池中一条连接完成）。"""
    dsn = dsn or _resolve_dsn()
    pool = await asyncpg.create_pool(
        dsn,
        min_size=_POOL_MIN_SIZE,
        max_size=_POOL_MAX_SIZE,
        command_timeout=60,
    )
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_PG)
        for migration in MIGRATIONS:
            try:
                await conn.execute(migration)
            except Exception as exc:
                logger.warning("数据库迁移跳过（%s）: %s", migration[:60], exc)
    logger.info("PostgreSQL 连接池已初始化: %s:%s", settings.pg_host, settings.pg_port)
    return pool


async def init_db() -> BaseConn:
    """初始化数据库（PostgreSQL，幂等建表）。已有连接池时直接返回。"""
    global _pool, _db
    if _pool is not None:
        return _db
    _pool = await _init_pool()
    _db = PooledConn(_pool)
    return _db


async def close_db() -> None:
    global _pool, _db
    if _pool is not None:
        await _pool.close()
        _pool = None
    _db = None


def get_db() -> BaseConn:
    if _db is None:
        raise RuntimeError("数据库尚未初始化")
    return _db
