"""统一日志配置：控制台 + 文件（按天轮转）。"""
from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_CONFIGURED = False


def setup_logging(level: int = logging.INFO, log_dir: str | None = None) -> None:
    """初始化日志。默认写入 `<项目>/data/logs/`（按天轮转，保留 30 天）。"""
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")

    # 控制台
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.handlers.clear()
    root.addHandler(console)

    # 文件（可配置目录，默认 data/logs）
    dir_str = log_dir or str(Path(__file__).resolve().parents[3] / "data" / "logs")
    log_path = Path(dir_str)
    try:
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            str(log_path / "app.log"), when="midnight", backupCount=30, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # 无法写日志目录时不阻断启动
        pass

    # 降低第三方库噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)