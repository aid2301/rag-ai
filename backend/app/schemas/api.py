"""API Schema。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str | None = None
    mode: str | None = None  # fast | standard | deep


class CitationOut(BaseModel):
    index: int
    document_id: str
    document_title: str
    section: str
    page: int | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationOut] = []
    mode: str = "standard"
    validation: dict | None = None
    token_usage: list[dict] = []
    debug: Any = None
    error: bool = False
    # 回答状态：answered / insufficient_knowledge / model_error / retrieval_error
    answer_status: str = "answered"
    insufficient_reason: str | None = None
    message_id: str | None = None


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationRename(BaseModel):
    title: str


class DocumentStatusUpdate(BaseModel):
    status: str  # ready | disabled


class SettingsUpdate(BaseModel):
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout: float | None = None
    llm_temperature: float | None = None
    llm_max_tokens: int | None = None
    default_chat_mode: str | None = None  # auto | fast | standard | deep
    show_thinking: bool | None = None


class AdminLogin(BaseModel):
    username: str
    password: str