"""GatingML 互操作与统计导出测试。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES_FCS = str(_PROJECT_ROOT / "examples" / "fcs" / "101_DEN084Y5_15_E01_008_clean.fcs")
EXAMPLES_ICS = str(_PROJECT_ROOT / "examples" / "gatingml" / "8_color_ICS.xml")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def file_id(client: TestClient) -> str:
    with open(EXAMPLES_FCS, "rb") as fh:
        resp = client.post(
            "/api/files/upload",
            files={"file": ("101_DEN084Y5_15_E01_008_clean.fcs", fh, "application/octet-stream")},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["file_id"]


@pytest.fixture(scope="module")
def gated_file_id(client: TestClient, file_id: str) -> str:
    """上传示例并保存一组门控，供导出/CSV 测试复用。"""
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
    resp = client.put(f"/api/files/{file_id}/gates", json=payload)
    assert resp.status_code == 200
    return file_id


class TestGatingMlExport:
    def test_export_xml(self, client: TestClient, gated_file_id: str):
        resp = client.get(f"/api/files/{gated_file_id}/gatingml")
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/xml")
        body = resp.content.decode("utf-8")
        assert "Gating-ML" in body
        assert "RectangleGate" in body
        # 层次：子门带 parent_id
        assert 'gating:parent_id="全部事件"' in body
        assert 'gating:id="淋巴细胞"' in body

    def test_export_empty(self, client: TestClient, file_id: str):
        resp = client.get(f"/api/files/{file_id}/gatingml")
        # file_id 是 gated_file_id 的源文件，已被写入门控（module 共享）
        # 用一个全新文件验证空门控 → 404
        with open(EXAMPLES_FCS, "rb") as fh:
            up = client.post(
                "/api/files/upload",
                files={"file": ("empty.fcs", fh, "application/octet-stream")},
            )
        fresh_id = up.json()["file_id"]
        resp = client.get(f"/api/files/{fresh_id}/gatingml")
        assert resp.status_code == 404


class TestGatingMlImport:
    def test_roundtrip(self, client: TestClient, gated_file_id: str):
        """导出 → 导入，门控结构应保持一致。"""
        exported = client.get(f"/api/files/{gated_file_id}/gatingml").content
        resp = client.post(
            f"/api/files/{gated_file_id}/gatingml/import",
            files={"file": ("gates.xml", exported, "application/xml")},
        )
        assert resp.status_code == 200, resp.text
        gates = resp.json()["gates"]
        by_name = {g["name"]: g for g in gates}
        assert "淋巴细胞" in by_name
        assert "全部事件" in by_name
        # 层次恢复：淋巴细胞 的父是 全部事件
        parent = by_name["淋巴细胞"]["parent_id"]
        assert parent is not None
        assert by_name["全部事件"]["id"] == parent

    def test_import_official_ics(self, client: TestClient, file_id: str):
        """导入 FlowKit 官方 8 色 ICS 的 GatingML 层级门控。"""
        with open(EXAMPLES_ICS, "rb") as fh:
            resp = client.post(
                f"/api/files/{file_id}/gatingml/import",
                files={"file": ("8_color_ICS.xml", fh, "application/xml")},
            )
        assert resp.status_code == 200, resp.text
        gates = resp.json()["gates"]
        names = {g["name"] for g in gates}
        assert {"TimeGate", "Singlets", "aAmine-", "CD3-pos", "CD4-pos", "CD8-pos"} <= names

        # 层次：CD4-pos 的父是 CD3-pos
        by_name = {g["name"]: g for g in gates}
        cd3 = by_name["CD3-pos"]
        cd4 = by_name["CD4-pos"]
        assert cd4["parent_id"] == cd3["id"]
        # CD3-pos 的父是 aAmine-
        assert cd3["parent_id"] == by_name["aAmine-"]["id"]

    def test_import_invalid(self, client: TestClient, file_id: str):
        resp = client.post(
            f"/api/files/{file_id}/gatingml/import",
            files={"file": ("bad.xml", b"<not-gatingml/>", "application/xml")},
        )
        assert resp.status_code == 400


class TestStatisticsCsv:
    def test_csv(self, client: TestClient, gated_file_id: str):
        resp = client.get(f"/api/files/{gated_file_id}/statistics.csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        text = resp.content.decode("utf-8-sig")
        lines = text.strip().splitlines()
        assert lines[0].startswith("gate_id,gate_name")
        assert len(lines) == 3  # 表头 + 2 个门
        assert "淋巴细胞" in text
        assert "全部事件" in text
        # 全部事件应覆盖 100%
        row = [l for l in lines if "全部事件" in l][0]
        assert "100.0000" in row

    def test_csv_empty(self, client: TestClient, file_id: str):
        # file_id 已有门控（module 共享 fixture 先 PUT 了？没有——file_id 只上传没存门控）
        # 用一个无门控文件验证 404
        with open(EXAMPLES_FCS, "rb") as fh:
            up = client.post(
                "/api/files/upload",
                files={"file": ("nofcs.fcs", fh, "application/octet-stream")},
            )
        fresh_id = up.json()["file_id"]
        resp = client.get(f"/api/files/{fresh_id}/statistics.csv")
        assert resp.status_code == 404
