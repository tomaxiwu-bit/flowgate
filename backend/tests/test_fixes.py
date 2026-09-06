"""第二轮审计修复的回归测试。

覆盖：P0-N1（缓存 LRU / DELETE API）、P0-N2（Docker 配置静态检查）、
P1-N1（GatingML 自包含补偿矩阵）、P1-N2（补偿状态暴露）、
P1-N4（gating:id NCName）、P1-N5（XXE forbid_dtd）、
P1-N6（荧光通道门控 E2E）、P2-N1（流式上传）、P2-N5（上传边界）。
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.lru import LRUCache
from app.main import app
from app.services import fcs_service
from app.services.gml_service import _slug_id
from app.services.sample_cache import get_sample

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


class TestLRUCache:
    """P0-N1：缓存必须有界。"""

    def test_evicts_least_recently_used(self):
        cache = LRUCache[str, int](maxsize=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")  # a 变最近使用
        cache.put("c", 3)  # 淘汰 b
        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3

    def test_put_existing_moves_to_end(self):
        cache = LRUCache[str, int](maxsize=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("a", 10)
        cache.put("c", 3)  # 淘汰 b（a 刚被更新）
        assert cache.get("a") == 10
        assert cache.get("b") is None


class TestDeleteApi:
    """P0-N1：DELETE 必须清缓存、数据目录与门控文件。"""

    @pytest.fixture()
    def own_file_id(self, client: TestClient) -> str:
        """独立上传的文件，避免删除操作污染共享 fixture。"""
        with open(EXAMPLES_FCS, "rb") as fh:
            resp = client.post(
                "/api/files/upload",
                files={"file": ("delete_me.fcs", fh, "application/octet-stream")},
            )
        assert resp.status_code == 200, resp.text
        yield resp.json()["file_id"]

    def test_delete_removes_file_and_caches(self, client: TestClient, own_file_id: str):
        # 先触发缓存加载
        assert client.get(f"/api/files/{own_file_id}/events?x=FSC-A&y=SSC-A&limit=100").status_code == 200
        assert get_sample(own_file_id) is not None

        resp = client.delete(f"/api/files/{own_file_id}")
        assert resp.status_code == 204

        # 缓存已清
        from app.services.sample_cache import _SAMPLE_CACHE

        assert own_file_id not in _SAMPLE_CACHE
        # 元信息 404
        assert client.get(f"/api/files/{own_file_id}").status_code == 404
        # 事件 404
        assert client.get(f"/api/files/{own_file_id}/events?x=FSC-A&y=SSC-A&limit=100").status_code == 404

    def test_delete_unknown_file_404(self, client: TestClient):
        assert client.delete("/api/files/does-not-exist").status_code == 404


class TestUploadBounds:
    """P2-N5：扩展名与大小上限必须有测试保护。"""

    def test_upload_rejects_non_fcs(self, client: TestClient):
        resp = client.post(
            "/api/files/upload",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 400
        assert "仅支持 FCS" in resp.json()["detail"]

    def test_upload_rejects_oversized(self, client: TestClient, monkeypatch):
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "max_upload_mb", 0)  # 上限 0 → 任何内容都超限
        resp = client.post(
            "/api/files/upload",
            files={"file": ("big.fcs", b"x" * 2048, "application/octet-stream")},
        )
        assert resp.status_code == 413
        monkeypatch.undo()


class TestCompensationState:
    """P1-N2：compensation_applied 与 has_spillover 分离，且暴露到接口。"""

    def test_upload_summary_reports_applied(self, client: TestClient, file_id: str):
        resp = client.get(f"/api/files/{file_id}")
        assert resp.status_code == 200
        summary = resp.json()
        assert summary["has_spillover"] is True
        assert summary["compensation_applied"] is True

    def test_events_no_fallback_when_comp_ok(self, client: TestClient, file_id: str):
        resp = client.get(f"/api/files/{file_id}/events?x=FSC-A&y=SSC-A&limit=100")
        assert resp.status_code == 200
        assert resp.json()["uncompensated_fallback"] is False

    def test_events_fallback_when_comp_fails(self, client: TestClient, monkeypatch):
        """强制补偿失败，验证前端告警字段（用独立文件，避免污染共享 fixture）。"""
        from app.services import sample_cache

        with open(EXAMPLES_FCS, "rb") as fh:
            resp = client.post(
                "/api/files/upload",
                files={"file": ("fallback.fcs", fh, "application/octet-stream")},
            )
        assert resp.status_code == 200
        own_id = resp.json()["file_id"]
        try:
            monkeypatch.setattr(sample_cache, "attach_compensation", lambda s: False)
            sample_cache.evict(own_id)  # 只清缓存让 get_sample 重走补偿（不删磁盘）
            resp = client.get(f"/api/files/{own_id}/events?x=FSC-A&y=SSC-A&limit=100")
            assert resp.status_code == 200
            assert resp.json()["uncompensated_fallback"] is True
            assert resp.json()["compensated"] is False
        finally:
            monkeypatch.undo()
            sample_cache.drop_sample(own_id)


class TestFluorescenceGateE2E:
    """P1-N6：荧光通道门控必须端到端验证（此前全部门测试只在 FSC/SSC）。"""

    def test_compensation_changes_fluorescence_gating(self, file_id: str):
        """同一荧光门坐标在补偿前/后的事件数必须显著不同。"""
        from flowkit._models.dimension import Dimension
        from flowkit._models.gates._gates import RectangleGate

        sample = get_sample(file_id)
        labels = list(sample.pnn_labels)
        # 高表达区（探查：100-60000 门区补偿前后差约 3.5 万事件）
        gate = RectangleGate(
            "t",
            [
                Dimension("TNFa FITC FLR-A", range_min=100, range_max=60000),
                Dimension("IFNg APC FLR-A", range_min=100, range_max=60000),
            ],
        )
        df_comp = pd.DataFrame(sample.get_events(source="comp"), columns=labels)
        df_raw = pd.DataFrame(sample.get_events(source="raw"), columns=labels)

        count_comp = int(np.asarray(gate.apply(df_comp)).sum())
        count_raw = int(np.asarray(gate.apply(df_raw)).sum())
        # 补偿显著改变荧光门控结果
        assert abs(count_comp - count_raw) > 10000, (
            f"补偿未显著影响荧光门控结果（comp={count_comp}, raw={count_raw}）"
        )

    def test_evaluate_on_fluorescence_channels(self, client: TestClient, file_id: str):
        """HTTP 级：在荧光通道画门并评估，补偿后阳性率落在合理区间。"""
        payload = {
            "gates": [
                {
                    "id": "fl1",
                    "name": "TNFa IFNg 双阳",
                    "type": "rect",
                    "x_label": "TNFa FITC FLR-A",
                    "y_label": "IFNg APC FLR-A",
                    "x_min": 100,
                    "x_max": 30000,
                    "y_min": 100,
                    "y_max": 30000,
                    "parent_id": None,
                }
            ]
        }
        resp = client.post(f"/api/files/{file_id}/gates/evaluate", json=payload)
        assert resp.status_code == 200, resp.text
        ev = resp.json()[0]
        assert 30.0 < ev["absolute_percent"] < 60.0, f"荧光阳性率异常: {ev}"
        assert ev["uncompensated_fallback"] is False


class TestGatingIdSlug:
    """P1-N4：导出 gating:id 必须是合法 NCName（无空格/括号）。"""

    def test_slug_removes_illegal_chars(self):
        assert " " not in _slug_id("淋巴细胞 (CD4)")
        assert "(" not in _slug_id("淋巴细胞 (CD4)")
        assert _slug_id("淋巴细胞 (CD4)") == "淋巴细胞_CD4"
        assert _slug_id("123门")[0] == "_"  # 不能以数字开头

    def test_export_xml_has_valid_ids(self, client: TestClient, file_id: str):
        payload = {
            "gates": [
                {
                    "id": "a1",
                    "name": "淋巴细胞 CD4 阳性",
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
        xml = client.get(f"/api/files/{file_id}/gatingml").text
        import re

        for gid in re.findall(r'gating:id="([^"]+)"', xml):
            assert " " not in gid, f"非法 gating:id 含空格: {gid}"
            assert "(" not in gid and ")" not in gid


class TestGatingmlSelfContained:
    """P1-N1：导出 XML 必须自包含补偿矩阵（spectrumMatrix），
    compensation-ref 不能是悬挂引用。"""

    def test_export_contains_spectrum_matrix(self, client: TestClient, file_id: str):
        payload = {
            "gates": [
                {
                    "id": "a1",
                    "name": "singlets",
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
        xml = client.get(f"/api/files/{file_id}/gatingml").text
        assert "spectrumMatrix" in xml, "导出 XML 缺少自包含补偿矩阵"
        assert 'compensation-ref="spill"' in xml, "门坐标应引用文档内补偿矩阵"
        # fluorochrome 名非空（P2-N8）
        assert "<data-type:fluorochrome></data-type:fluorochrome>" not in xml


class TestXxeForbidDtd:
    """P1-N5：任何 DOCTYPE（含 UTF-16 / 注释填充）都必须在解析层拒绝。"""

    _DTD = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///C:/Windows/win.ini">]>'

    def test_import_doctype_rejected_utf8(self, client: TestClient, file_id: str):
        payload = b'<?xml version="1.0"?>' + self._DTD + b"<gating:Gating-ML/>"
        resp = client.post(
            f"/api/files/{file_id}/gatingml/import",
            files={"file": ("evil.xml", payload, "application/xml")},
        )
        assert resp.status_code == 400

    def test_import_doctype_rejected_utf16(self, client: TestClient, file_id: str):
        # UTF-16LE：字节扫描式预检会失明，解析层 forbid_dtd 必须兜住
        payload = '<?xml version="1.0" encoding="UTF-16"?>' + self._DTD.decode() + "<gating:Gating-ML/>"
        payload = payload.encode("utf-16")
        resp = client.post(
            f"/api/files/{file_id}/gatingml/import",
            files={"file": ("evil16.xml", payload, "application/xml")},
        )
        assert resp.status_code == 400

    def test_import_doctype_rejected_after_comment_padding(self, client: TestClient, file_id: str):
        # 注释填充越过任何固定字节窗口
        padding = b"<!--" + b"x" * 5000 + b"-->"
        payload = b'<?xml version="1.0"?>' + padding + self._DTD + b"<gating:Gating-ML/>"
        resp = client.post(
            f"/api/files/{file_id}/gatingml/import",
            files={"file": ("evil3.xml", payload, "application/xml")},
        )
        assert resp.status_code == 400


class TestDockerConfigStatic:
    """P0-N2：Docker 远程部署配置（build 时注入 + CORS 可配）静态检查。"""

    def test_frontend_dockerfile_has_build_arg(self):
        dockerfile = _PROJECT_ROOT / "frontend" / "Dockerfile"
        text = dockerfile.read_text(encoding="utf-8")
        assert "ARG NEXT_PUBLIC_API_BASE_URL" in text
        assert "ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL" in text

    def test_compose_passes_build_arg(self):
        compose = _PROJECT_ROOT / "docker-compose.yml"
        text = compose.read_text(encoding="utf-8")
        assert "NEXT_PUBLIC_API_BASE_URL" in text
        assert "build:" in text and "args:" in text

    def test_cors_origins_configurable(self):
        from app.core.config import Settings

        s = Settings(cors_origins="https://demo.example.com,http://localhost:3000")
        assert s.cors_origin_list == ["https://demo.example.com", "http://localhost:3000"]
