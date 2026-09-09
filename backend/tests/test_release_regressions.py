"""Regression coverage for release preparation changes."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from app.core.config import Settings, settings
from app.core import security
from app.db.database import _resolve_dsn
from tests.db_helpers import test_database_url as get_test_database_url


def test_database_password_is_url_encoded(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "pg_password", "test@:/#%password")
    assert unquote(urlsplit(_resolve_dsn()).password) == "test@:/#%password"


def test_test_database_rejects_application_database(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://kb:kb@localhost/kb")
    with pytest.raises(ValueError, match="disposable"):
        get_test_database_url()


def test_secret_key_can_be_read_from_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-dotenv-secret\n", encoding="utf-8")
    assert Settings(_env_file=env_file).secret_key == "test-dotenv-secret"


def test_unwritable_secret_directory_uses_same_process_key(tmp_path, monkeypatch):
    file = tmp_path / "not-a-directory"
    file.write_text("occupied", encoding="utf-8")
    monkeypatch.setattr(settings, "data_dir", str(file))
    monkeypatch.setattr(settings, "secret_key", "")
    security.get_secret_key.cache_clear()
    try:
        assert security.get_secret_key() == security.get_secret_key()
    finally:
        security.get_secret_key.cache_clear()


def load_evaluation():
    path = Path(__file__).resolve().parents[2] / "scripts" / "evaluate.py"
    spec = importlib.util.spec_from_file_location("release_evaluation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_evaluation_failure_still_writes_metrics(tmp_path, monkeypatch):
    module = load_evaluation()
    dataset = tmp_path / "questions.json"
    dataset.write_text(json.dumps([{"question": "example"}]), encoding="utf-8")
    closed = []
    async def init():
        pass
    async def close():
        closed.append(True)
    async def fail(*args, **kwargs):
        raise RuntimeError("simulated model outage")
    monkeypatch.setattr(module, "init_db", init)
    monkeypatch.setattr(module, "close_db", close)
    monkeypatch.setattr(module.RAGPipeline, "answer", fail)
    result = await module.run(str(dataset), None, None)
    assert result["summary"]["failed"] == 1
    assert result["summary"]["evaluated"] == 0
    assert "simulated model outage" in result["results"][0]["error"]
    assert closed == [True]


def test_spa_cannot_serve_files_outside_dist(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.core import config

    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("demo app", encoding="utf-8")
    (dist.parent / "private.txt").write_text("private content", encoding="utf-8")
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    entry = Path(__file__).resolve().parents[1] / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("release_main", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # No lifespan is needed for static route tests.
    client = TestClient(module.app)
    assert client.get("/").text == "demo app"
    assert client.get("/..%2Fprivate.txt").status_code == 404
