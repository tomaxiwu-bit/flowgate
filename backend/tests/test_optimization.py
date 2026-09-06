"""P0/P1 优化验证：补偿、logicle、安全修复。

覆盖审计报告第一阶段要点：
- P0-1 荧光补偿（$SPILLOVER 自动应用）
- P0-2 logicle 显示变换
- P1-4 CSV injection 防护
- P1-5 上传路径遍历防护
- P1-7 畸形 FCS 头事件数上限
- P1-1 门名白名单（中文/ASCII 安全字符）
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import fcs_service
from app.api.export import _sanitize_csv_field

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES_FCS = str(_PROJECT_ROOT / "examples" / "fcs" / "101_DEN084Y5_15_E01_008_clean.fcs")


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def file_id(client: TestClient) -> str:
    with open(EXAMPLES_FCS, "rb") as fh:
        resp = client.post(
            "/api/files/upload",
            files={"file": ("101_DEN084Y5_15_E01_008_clean.fcs", fh, "application/octet-stream")},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["file_id"]


class TestCompensation:
    """P0-1：$SPILLOVER 自动补偿。"""

    def test_upload_reports_spillover(self, client: TestClient, file_id: str):
        resp = client.get(f"/api/files/{file_id}")
        assert resp.status_code == 200
        assert resp.json()["has_spillover"] is True

    def test_events_default_compensated(self, client: TestClient, file_id: str):
        resp = client.get(
            f"/api/files/{file_id}/events",
            params={"x": "FSC-A", "y": "CD4 PE-Cy7 FLR-A"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["compensated"] is True
        assert data["data_space"] == "comp"

    def test_compensated_differs_from_raw_on_fluorescence(self, client: TestClient, file_id: str):
        """荧光通道补偿前后应不同（示例文件含真实 spillover）。"""
        params = {"x": "FSC-A", "y": "CD4 PE-Cy7 FLR-A", "limit": 20000}
        comp = client.get(f"/api/files/{file_id}/events", params=params).json()
        raw = client.get(
            f"/api/files/{file_id}/events", params={**params, "compensate": "false"}
        ).json()
        assert raw["compensated"] is False
        assert raw["data_space"] == "raw"
        # 补偿改变荧光通道数值
        diff = max(abs(a - b) for a, b in zip(comp["y"], raw["y"]))
        assert diff > 1.0, f"补偿前后荧光通道应不同，max diff={diff}"

    def test_events_logicle_transform(self, client: TestClient, file_id: str):
        resp = client.get(
            f"/api/files/{file_id}/events",
            params={"x": "FSC-A", "y": "CD4 PE-Cy7 FLR-A", "transform": "logicle"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_space"] == "logicle"
        # logicle 输出应为有界数值（一般落在 [0, ~1.2]）
        assert all(-2.0 < v < 5.0 for v in data["x"][:100])
        assert all(-2.0 < v < 5.0 for v in data["y"][:100])

    def test_events_bad_transform(self, client: TestClient, file_id: str):
        resp = client.get(
            f"/api/files/{file_id}/events",
            params={"x": "FSC-A", "y": "SSC-A", "transform": "bogus"},
        )
        assert resp.status_code == 400


class TestSecurity:
    """P1-4 / P1-5 / P1-7。"""

    def test_upload_path_traversal_sanitized(self, client: TestClient, tmp_path):
        """文件名含 ../ 时只取 basename，杜绝越界写。"""
        with open(EXAMPLES_FCS, "rb") as fh:
            resp = client.post(
                "/api/files/upload",
                files={"file": ("..\\..\\evil.fcs", fh, "application/octet-stream")},
            )
        assert resp.status_code == 200, resp.text
        fid = resp.json()["file_id"]
        # 文件应落在 uploads/<uuid>/evil.fcs
        from app.core.config import get_settings

        dest = get_settings().upload_dir / fid / "evil.fcs"
        assert dest.is_file()
        # 且 uploads 根目录不应出现 evil.fcs
        assert not (get_settings().upload_dir / "evil.fcs").exists()

    def test_gate_name_formula_rejected(self, client: TestClient, file_id: str):
        payload = {
            "gates": [
                {
                    "id": "g1",
                    "name": "=SUM(A1:A2)",
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
        resp = client.put(f"/api/files/{file_id}/gates", json=payload)
        assert resp.status_code == 422  # Pydantic pattern 拒绝公式注入名

    def test_gate_name_chinese_and_hyphen_ok(self, client: TestClient, file_id: str):
        payload = {
            "gates": [
                {
                    "id": "g1",
                    "name": "淋巴细胞-1 (CD4)",
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
        resp = client.put(f"/api/files/{file_id}/gates", json=payload)
        assert resp.status_code == 200

    def test_sanitize_csv_field(self):
        assert _sanitize_csv_field("=SUM(A1)") == "'=SUM(A1)"
        assert _sanitize_csv_field("+123") == "'+123"
        assert _sanitize_csv_field("正常门名") == "正常门名"
        assert _sanitize_csv_field("CD4+") == "CD4+"

    def test_csv_export_no_injection(self, client: TestClient, file_id: str):
        """门名以 - 开头（白名单允许）导出时被净化。"""
        payload = {
            "gates": [
                {
                    "id": "d1",
                    "name": "-danger",
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
        resp = client.get(f"/api/files/{file_id}/statistics.csv")
        assert resp.status_code == 200
        body = resp.content.decode("utf-8-sig")
        assert "'-danger" in body

    def test_malformed_huge_event_count_rejected(self, monkeypatch):
        """畸形 FCS 头（$TOT 虚高）在解析层被拒。"""
        import pathlib

        import flowkit

        class FakeSample:
            pnn_labels = ["FSC-A", "SSC-A"]
            pns_labels = []
            channel_count = 2
            event_count = 99_999_999
            measurements = None

            def get_metadata(self):
                return {}

        monkeypatch.setattr(flowkit, "Sample", lambda *a, **k: FakeSample())
        with pytest.raises(fcs_service.FcsParseError, match="超过上限"):
            fcs_service.parse_fcs_file(pathlib.Path("fake.fcs"), "fake.fcs")
