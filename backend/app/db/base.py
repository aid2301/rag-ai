"""数据库访问抽象接口。

所有业务代码只依赖本接口（而非具体驱动连接），由 PostgreSQL 实现
（asyncpg）提供。接口方法命名保持 execute / execute_fetchall /
execute_fetchone / executemany / commit / close。
"""
from __future__ import annotations

from typing import Any, Sequence

from app.core.logging import get_logger

logger = get_logger(__name__)


class BaseConn:
    """数据库连接的统一接口（子类实现全部方法）。"""

    def __init__(self, driver: str) -> None:
        self.driver = driver

    async def execute(self, sql: str, parameters: Sequence[Any] = ()) -> Any:
        raise NotImplementedError

    async def execute_fetchall(self, sql: str, parameters: Sequence[Any] = ()) -> list[dict]:
        raise NotImplementedError

    async def execute_fetchone(self, sql: str, parameters: Sequence[Any] = ()) -> dict | None:
        raise NotImplementedError

    async def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> Any:
        raise NotImplementedError

    async def commit(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError

    async def row_count(self, result: Any) -> int:
        """从任意 execute 结果中提取影响行数（驱动差异屏蔽）。"""
        if result is None:
            return 0
        if hasattr(result, "rowcount") and result.rowcount is not None:
            try:
                return int(result.rowcount)
            except (TypeError, ValueError):
                return 0
        return 0