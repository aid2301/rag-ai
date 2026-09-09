"""PostgreSQL 连接适配（asyncpg）。

业务 SQL 中使用的 `?` 占位符在 asyncpg 中需转换为 `$1/$2/...`，
本层自动完成转换，使业务代码无需感知数据库差异。
"""
from __future__ import annotations

import re
from typing import Any, Sequence

import asyncpg

from app.core.logging import get_logger
from app.db.base import BaseConn

logger = get_logger(__name__)

# 将 SQLite 风格 ? 占位符转换为 asyncpg 的 $N 风格
_PLACEHOLDER_RE = re.compile(r"\?")


class PGConn(BaseConn):
    def __init__(self, conn: asyncpg.Connection) -> None:
        super().__init__(driver="postgres")
        self._conn = conn

    @staticmethod
    def _translate(sql: str) -> str:
        """把 ? 占位符替换为 $1..$N（跳过字符串字面量中的 ?）。"""
        if "?" not in sql:
            return sql
        out: list[str] = []
        i = 0
        n = 0
        in_str = False
        quote: str | None = None
        while i < len(sql):
            ch = sql[i]
            if in_str:
                out.append(ch)
                if ch == quote:
                    # 处理转义引号（'' 或 \"）
                    if i + 1 < len(sql) and sql[i + 1] == quote:
                        out.append(sql[i + 1])
                        i += 1
                    else:
                        in_str = False
                        quote = None
            else:
                if ch in ("'", '"'):
                    in_str = True
                    quote = ch
                    out.append(ch)
                elif ch == "?":
                    n += 1
                    out.append(f"${n}")
                else:
                    out.append(ch)
            i += 1
        return "".join(out)

    async def execute(self, sql: str, parameters: Sequence[Any] = ()) -> Any:
        result = await self._conn.execute(self._translate(sql), *parameters)
        return result  # asyncpg ELECT () 字符串

    async def execute_fetchall(self, sql: str, parameters: Sequence[Any] = ()) -> list[dict]:
        rows = await self._conn.fetch(self._translate(sql), *parameters)
        return [dict(r) for r in rows]

    async def execute_fetchone(self, sql: str, parameters: Sequence[Any] = ()) -> dict | None:
        row = await self._conn.fetchrow(self._translate(sql), *parameters)
        return dict(row) if row is not None else None

    async def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> Any:
        # asyncpg 没有 executemany，改用事务内逐条 execute
        tr = self._conn.transaction()
        await tr.start()
        try:
            for params in seq_of_params:
                await self._conn.execute(self._translate(sql), *params)
            await tr.commit()
        except Exception:
            await tr.rollback()
            raise

    async def commit(self) -> None:
        # asyncpg 的 autocommit；显式 commit 为空操作（事务由 execute 自动管理）
        pass

    async def close(self) -> None:
        await self._conn.close()