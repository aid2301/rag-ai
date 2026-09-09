"""统一签名密钥（token 持久化）。

用户 access_token 与管理员 access_token 使用同一把 HMAC 签名密钥。
密钥解析优先级：
1. 环境变量 `SECRET_KEY`（部署时显式注入，最优先）；
2. `data/secret_key` 文件（首次启动自动生成 64 位 hex 并持久化，
   之后重启读取同一把密钥，保证 token 重启后仍然有效）；
3. 文件系统不可写时回退为进程级随机密钥（重启失效，但不至于崩溃）。

user_auth.py 与 admin.py 均通过 `get_secret_key()` 获取同一把密钥。
"""
from __future__ import annotations

from functools import lru_cache
import secrets
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_SECRET_FILE_NAME = "secret_key"


@lru_cache(maxsize=1)
def get_secret_key() -> str:
    """返回统一 HMAC 签名密钥（环境变量优先，否则持久化到 data/secret_key）。"""
    env_key = settings.secret_key.strip()
    if env_key:
        return env_key

    path = Path(settings.data_dir) / _SECRET_FILE_NAME
    try:
        if path.exists():
            key = path.read_text(encoding="utf-8").strip()
            if key:
                return key
        path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32)
        path.write_text(key, encoding="utf-8")
        logger.info("已生成并持久化签名密钥: %s", path)
        return key
    except OSError:
        # 目录不可写：回退为进程级随机密钥（重启后 token 失效，但不崩溃）
        logger.warning("无法写入密钥文件 %s，使用进程级随机密钥", path)
        return secrets.token_hex(32)
