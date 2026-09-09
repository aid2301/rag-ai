"""统一异常处理。

将未捕获异常转为结构化 JSON 响应，并记录错误日志，避免向客户端暴露内部堆栈。
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    detail = errors[0]["msg"] if errors else "请求参数校验失败"
    return JSONResponse(status_code=422, content={"detail": detail})


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("未捕获异常: %s %s -> %r", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)