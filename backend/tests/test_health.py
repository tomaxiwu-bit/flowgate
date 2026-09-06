"""健康检查与基础路由测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    """健康检查应返回 ok。"""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


def test_root_info() -> None:
    """根路径应返回服务信息。"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "FlowGate API"
