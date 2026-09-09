"""新功能冒烟测试：用户登录、用户隔离、管理端用户管理。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.db_helpers import init_db_for_test


@pytest.fixture()
def client(monkeypatch):
    from app import main

    # Initialize the dedicated test database on TestClient's own event loop.
    monkeypatch.setattr(main, "init_db", init_db_for_test)
    with TestClient(main.app) as client:
        yield client


def _login(client: TestClient, username: str, password: str):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_login_and_me(client: TestClient):
    r = client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
    assert r.status_code == 401  # 用户不存在
    r = client.post("/api/admin/users", json={"username": "alice", "password": "secret1"})
    assert r.status_code == 403  # 未登录管理员

    # 管理员登录
    admin_r = client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    assert admin_r.status_code == 200, admin_r.text
    admin_token = admin_r.json()["token"]

    # 添加用户
    r = client.post(
        "/api/admin/users",
        json={"username": "alice", "password": "secret1", "display_name": "爱丽丝"},
        headers=_auth(admin_token),
    )
    assert r.status_code == 200, r.text
    r = client.post(
        "/api/admin/users",
        json={"username": "alice", "password": "secret1"},
        headers=_auth(admin_token),
    )
    assert r.status_code == 400  # 重名

    # 用户登录
    token = _login(client, "alice", "secret1")
    r = client.get("/api/auth/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["username"] == "alice"

    # 错误密码
    r = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
    assert r.status_code == 401


def test_conversation_user_isolation(client: TestClient):
    admin_token = client.post(
        "/api/admin/login", json={"username": "admin", "password": "admin123"}
    ).json()["token"]
    for name, pwd in [("alice", "secret1"), ("bob", "secret2")]:
        client.post("/api/admin/users", json={"username": name, "password": pwd}, headers=_auth(admin_token))

    alice = _login(client, "alice", "secret1")
    bob = _login(client, "bob", "secret2")

    # alice 创建对话
    r = client.post("/api/conversations", json={}, headers=_auth(alice))
    assert r.status_code == 200, r.text
    conv_id = r.json()["id"]

    # alice 能看到自己的对话
    r = client.get("/api/conversations", headers=_auth(alice))
    assert len(r.json()) == 1

    # bob 看不到 alice 的对话
    r = client.get("/api/conversations", headers=_auth(bob))
    assert r.json() == []

    # bob 无法读取 alice 的对话消息
    r = client.get(f"/api/conversations/{conv_id}/messages", headers=_auth(bob))
    assert r.status_code == 404

    # 未登录 401
    r = client.get("/api/conversations")
    assert r.status_code == 401


def test_admin_user_management_and_usage(client: TestClient):
    admin_token = client.post(
        "/api/admin/login", json={"username": "admin", "password": "admin123"}
    ).json()["token"]
    for name, pwd in [("alice", "secret1"), ("bob", "secret2")]:
        client.post("/api/admin/users", json={"username": name, "password": pwd}, headers=_auth(admin_token))

    # 用户列表带用量
    r = client.get("/api/admin/users", headers=_auth(admin_token))
    users = {u["username"]: u for u in r.json()}
    assert "alice" in users and "bob" in users
    assert users["alice"]["total_tokens"] == 0

    # 无 LLM 配置时聊天返回友好错误，但会创建对话
    alice = _login(client, "alice", "secret1")
    r = client.post(
        "/api/chat",
        json={"query": "你好"},
        headers=_auth(alice),
    )
    assert r.status_code == 200
    assert r.json()["error"] is True

    # 管理端用量
    r = client.get("/api/admin/usage", headers=_auth(admin_token))
    assert r.status_code == 200
    assert isinstance(r.json()["by_user"], list)

    # 管理端查看 alice 的对话
    r = client.get("/api/admin/users", headers=_auth(admin_token))
    alice_id = next(u["id"] for u in r.json() if u["username"] == "alice")
    r = client.get(f"/api/admin/users/{alice_id}/conversations", headers=_auth(admin_token))
    assert len(r.json()) >= 1
    conv_id = r.json()[0]["id"]
    r = client.get(
        f"/api/admin/users/{alice_id}/conversations/{conv_id}/messages",
        headers=_auth(admin_token),
    )
    assert r.status_code == 200
    assert len(r.json()) >= 1

    # 重置密码
    r = client.post(
        f"/api/admin/users/{alice_id}/reset-password",
        json={"password": "newpass1"},
        headers=_auth(admin_token),
    )
    assert r.status_code == 200
    r = client.post("/api/auth/login", json={"username": "alice", "password": "newpass1"})
    assert r.status_code == 200

    # 删除用户后其对话消失
    r = client.delete(f"/api/admin/users/{alice_id}", headers=_auth(admin_token))
    assert r.status_code == 200
    r = client.get(f"/api/admin/users/{alice_id}/conversations", headers=_auth(admin_token))
    assert r.status_code == 404


def test_documents_upload_requires_admin(client: TestClient):
    """普通用户不可管理文档；仅管理员可上传/查看文档。"""
    admin_token = client.post(
        "/api/admin/login", json={"username": "admin", "password": "admin123"}
    ).json()["token"]
    client.post("/api/admin/users", json={"username": "alice", "password": "secret1"}, headers=_auth(admin_token))
    alice = _login(client, "alice", "secret1")

    # 普通用户上传被拒绝
    r = client.post(
        "/api/documents",
        files={"file": ("测试文档.txt", "这是测试内容".encode("utf-8"), "text/plain")},
        headers=_auth(alice),
    )
    assert r.status_code == 403, r.text
    # 未登录也拒绝
    r = client.post(
        "/api/documents",
        files={"file": ("测试文档.txt", "这是测试内容".encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 403, r.text

    # 管理员上传成功
    r = client.post(
        "/api/documents",
        files={"file": ("测试文档.txt", "这是测试内容".encode("utf-8"), "text/plain")},
        headers=_auth(admin_token),
    )
    assert r.status_code == 200, r.text
    doc_id = r.json()["document_id"]

    # 普通用户不可查看文档列表
    r = client.get("/api/documents", headers=_auth(alice))
    assert r.status_code == 403, r.text

    # 管理员可查看
    r = client.get("/api/documents", headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    docs = {d["id"]: d for d in r.json()}
    assert doc_id in docs
