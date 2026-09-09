"""Shared fixtures: no local document writes or live LLM calls."""
from __future__ import annotations

import os

# Set before test-module collection imports authentication modules.
os.environ["SECRET_KEY"] = "test-only-signing-key-never-use-in-production"

import pytest
from app.core.config import settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "data" / "documents"))
    monkeypatch.setattr(settings, "llm_base_url", "")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_model", "")
    monkeypatch.setattr(settings, "admin_password", "admin123")
