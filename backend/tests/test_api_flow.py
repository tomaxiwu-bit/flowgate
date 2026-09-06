"""events / gates 路由测试。

使用 examples/fcs 的真实示例文件走完整上传链路，验证取数与门控评估。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES_FCS = str(_PROJECT_ROOT / "examples" / "fcs" / "101_DEN084Y5_15_E01_008_clean.fcs")


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def file_id(client: TestClient) -> str:
    """通过上传接口上传示例 FCS，返回 file_id。"""
    with open(EXAMPLES_FCS, "rb") as fh:
        resp = client.post(
            "/api/files/upload",
            files={"file": ("101_DEN084Y5_15_E01_008_clean.fcs", fh, "application/octet-stream")},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["file_id"]


class TestEvents:
    def test_events_downsampled(self, client: TestClient, file_id: str):
        resp = client.get(f"/api/files/{file_id}/events", params={"x": "FSC-A", "y": "SSC-A"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 290172
        assert data["sampled"] == 20000
        assert len(data["x"]) == len(data["y"]) == 20000
        assert data["x_label"] == "FSC-A" and data["y_label"] == "SSC-A"

    def test_events_no_downsample(self, client: TestClient, file_id: str):
        resp = client.get(
            f"/api/files/{file_id}/events",
            params={"x": "FSC-A", "y": "SSC-A", "limit": 100000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sampled"] == 100000
        assert data["total_events"] == 290172

    def test_events_fluorescence_channel(self, client: TestClient, file_id: str):
        resp = client.get(
            f"/api/files/{file_id}/events",
            params={"x": "FSC-A", "y": "CD4 PE-Cy7 FLR-A"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["x"]) == 20000

    def test_events_bad_channel(self, client: TestClient, file_id: str):
        resp = client.get(f"/api/files/{file_id}/events", params={"x": "FSC-A", "y": "NOPE"})
        assert resp.status_code == 400

    def test_events_unknown_file(self, client: TestClient):
        resp = client.get("/api/files/doesnotexist/events", params={"x": "FSC-A", "y": "SSC-A"})
        assert resp.status_code == 404


class TestGates:
    def test_evaluate_rect(self, client: TestClient, file_id: str):
        payload = {
            "gates": [
                {
                    "id": "g1",
                    "name": "淋巴细胞",
                    "type": "rect",
                    "x_label": "FSC-A",
                    "y_label": "SSC-A",
                    "x_min": 30000,
                    "x_max": 100000,
                    "y_min": 20000,
                    "y_max": 80000,
                    "parent_id": None,
                }
            ]
        }
        resp = client.post(f"/api/files/{file_id}/gates/evaluate", json=payload)
        assert resp.status_code == 200, resp.text
        evals = resp.json()
        assert len(evals) == 1
        assert evals[0]["id"] == "g1"
        assert evals[0]["event_count"] > 0
        assert 0 < evals[0]["absolute_percent"] < 100

    def test_evaluate_hierarchy(self, client: TestClient, file_id: str):
        payload = {
            "gates": [
                {
                    "id": "p1",
                    "name": "全部事件",
                    "type": "rect",
                    "x_label": "FSC-A",
                    "y_label": "SSC-A",
                    "x_min": 0,
                    "x_max": 262144,
                    "y_min": 0,
                    "y_max": 262144,
                    "parent_id": None,
                },
                {
                    "id": "c1",
                    "name": "淋巴细胞",
                    "type": "rect",
                    "x_label": "FSC-A",
                    "y_label": "SSC-A",
                    "x_min": 30000,
                    "x_max": 100000,
                    "y_min": 20000,
                    "y_max": 80000,
                    "parent_id": "p1",
                },
            ]
        }
        resp = client.post(f"/api/files/{file_id}/gates/evaluate", json=payload)
        assert resp.status_code == 200, resp.text
        evals = {e["id"]: e for e in resp.json()}
        assert evals["p1"]["event_count"] == 290172
        assert evals["p1"]["absolute_percent"] == pytest.approx(100.0, abs=0.01)
        assert evals["c1"]["event_count"] <= evals["p1"]["event_count"]
        assert evals["c1"]["relative_percent"] <= 100.0

    def test_evaluate_polygon(self, client: TestClient, file_id: str):
        payload = {
            "gates": [
                {
                    "id": "poly1",
                    "name": "多边门",
                    "type": "polygon",
                    "x_label": "FSC-A",
                    "y_label": "SSC-A",
                    "vertices": [[30000, 20000], [30000, 80000], [100000, 80000], [100000, 20000]],
                    "parent_id": None,
                }
            ]
        }
        resp = client.post(f"/api/files/{file_id}/gates/evaluate", json=payload)
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["event_count"] > 0

    def test_save_and_get(self, client: TestClient, file_id: str):
        payload = {
            "gates": [
                {
                    "id": "s1",
                    "name": "保存测试",
                    "type": "rect",
                    "x_label": "FSC-A",
                    "y_label": "SSC-A",
                    "x_min": 1,
                    "x_max": 2,
                    "y_min": 1,
                    "y_max": 2,
                    "parent_id": None,
                }
            ]
        }
        assert client.put(f"/api/files/{file_id}/gates", json=payload).status_code == 200
        got = client.get(f"/api/files/{file_id}/gates").json()
        assert got["gates"][0]["id"] == "s1"

    def test_evaluate_bad_parent(self, client: TestClient, file_id: str):
        payload = {
            "gates": [
                {
                    "id": "orphan",
                    "name": "孤儿门",
                    "type": "rect",
                    "x_label": "FSC-A",
                    "y_label": "SSC-A",
                    "x_min": 1,
                    "x_max": 2,
                    "y_min": 1,
                    "y_max": 2,
                    "parent_id": "missing",
                }
            ]
        }
        resp = client.post(f"/api/files/{file_id}/gates/evaluate", json=payload)
        assert resp.status_code == 400
