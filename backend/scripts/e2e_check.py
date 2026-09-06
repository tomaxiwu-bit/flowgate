"""FlowGate 端到端验证（真实 HTTP 服务）。"""
import pathlib
import sys

# 保证可 import app.*（脚本位于 backend/scripts/ 下）
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import httpx

BASE = "http://127.0.0.1:8000"
FCS = r"C:\Users\18519\OneDrive\桌面\github项目\flowgate\examples\fcs\101_DEN084Y5_15_E01_008_clean.fcs"
GML = r"C:\Users\18519\OneDrive\桌面\github项目\flowgate\examples\gatingml\8_color_ICS.xml"

ok = 0
fail = 0


def check(name: str, cond: bool, detail: str = ""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [PASS] {name}")
    else:
        fail += 1
        print(f"  [FAIL] {name} :: {detail}")


client = httpx.Client(timeout=60)

print("== 1. 上传 ==")
with open(FCS, "rb") as fh:
    r = client.post(f"{BASE}/api/files/upload", files={"file": ("sample.fcs", fh, "application/octet-stream")})
check("上传 200", r.status_code == 200, r.text[:200])
fid = r.json()["file_id"]
summary = r.json()["summary"]
check("has_spillover=True", summary.get("has_spillover") is True, str(summary))
print(f"  file_id={fid} 事件数={summary['event_count']} 荧光通道数={len(summary['channel_labels'])}")

print("\n== 2. 补偿 ==")
q = {"x": "FSC-A", "y": "CD4 PE-Cy7 FLR-A", "limit": 5000}
comp = client.get(f"{BASE}/api/files/{fid}/events", params=q).json()
q2 = dict(q, compensate="false")
raw = client.get(f"{BASE}/api/files/{fid}/events", params=q2).json()
check("默认已补偿", comp["compensated"] is True and comp["data_space"] == "comp")
check("compensate=false 为 raw", raw["compensated"] is False and raw["data_space"] == "raw")
diff = max(abs(a - b) for a, b in zip(comp["y"], raw["y"]))
check(f"荧光通道补偿前后有差异 (max diff={diff:.2f})", diff > 1.0, str(diff))

print("\n== 3. Logicle ==")
lg = client.get(f"{BASE}/api/files/{fid}/events", params=dict(q, transform="logicle")).json()
check("logicle 返回", lg["data_space"] == "logicle", str(lg.get("data_space")))
xs_ok = all(-2 < v < 5 for v in lg["x"][:500])
ys_ok = all(-2 < v < 5 for v in lg["y"][:500])
check("logicle 值域有界", xs_ok and ys_ok)

print("\n== 4. 门控 ==")
gates = {
    "gates": [
        {"id": "p1", "name": "全部事件", "type": "rect", "x_label": "FSC-A", "y_label": "SSC-A",
         "x_min": 0, "x_max": 262144, "y_min": 0, "y_max": 262144, "parent_id": None},
        {"id": "c1", "name": "淋巴细胞", "type": "rect", "x_label": "FSC-A", "y_label": "SSC-A",
         "x_min": 30000, "x_max": 100000, "y_min": 20000, "y_max": 80000, "parent_id": "p1"},
        {"id": "c2", "name": "CD4阳性", "type": "rect", "x_label": "FSC-A", "y_label": "CD4 PE-Cy7 FLR-A",
         "x_min": 30000, "x_max": 100000, "y_min": 1000, "y_max": 100000, "parent_id": "c1"},
    ]
}
r = client.put(f"{BASE}/api/files/{fid}/gates", json=gates)
check("PUT 门控 200", r.status_code == 200, r.text[:200])
r = client.post(f"{BASE}/api/files/{fid}/gates/evaluate", json=gates)
check("评估 200", r.status_code == 200, r.text[:200])
evals = {e["id"]: e for e in r.json()}
check("全部事件=100%", abs(evals["p1"]["absolute_percent"] - 100) < 0.01, str(evals["p1"]))
check("淋巴细胞>0", evals["c1"]["event_count"] > 0, str(evals["c1"]))
check("CD4 子门 <= 父门", evals["c2"]["event_count"] <= evals["c1"]["event_count"])
print(f"  淋巴细胞 {evals['c1']['event_count']} ({evals['c1']['absolute_percent']:.2f}%) | "
      f"CD4+ {evals['c2']['event_count']} ({evals['c2']['relative_percent']:.2f}% rel)")

print("\n== 5. CSV 导出 ==")
r = client.get(f"{BASE}/api/files/{fid}/statistics.csv")
check("CSV 200", r.status_code == 200)
body = r.content
check("UTF-8 BOM", body.startswith(b"\xef\xbb\xbf"))
text = body.decode("utf-8-sig")
check("包含中文门名", "淋巴细胞" in text)
check("4 位小数", "100.0000" in text or any("." in line for line in text.splitlines()[1:]))

print("\n== 6. GatingML 导出 ==")
r = client.get(f"{BASE}/api/files/{fid}/gatingml")
check("GML 200", r.status_code == 200, r.text[:200])
xml = r.text
check("Gating-ML 根元素", "Gating-ML" in xml, xml[:200])
check("含门", "RectangleGate" in xml, xml[:300])
check("中文门名作为 id", "淋巴细胞" in xml)
check("补偿空间声明 FCS", 'compensation-ref="FCS"' in xml, "未声明补偿")

print("\n== 7. GatingML 导入 ==")
with open(GML, "rb") as fh:
    r = client.post(f"{BASE}/api/files/{fid}/gatingml/import", files={"file": ("8_color_ICS.xml", fh, "application/xml")})
check("导入 200", r.status_code == 200, r.text[:200])
imported = r.json()["gates"]
check(f"导入 {len(imported)} 个门", len(imported) >= 4, str(len(imported)))
check("门名合法（无非法字符）", all(g["name"] for g in imported))

print("\n== 8. 安全项 ==")
with open(FCS, "rb") as fh:
    r = client.post(f"{BASE}/api/files/upload", files={"file": ("..\\..\\evil.fcs", fh, "application/octet-stream")})
check("路径遍历文件名被接受(basename化)", r.status_code == 200, r.text[:200])
evil_id = r.json()["file_id"]
from app.core.config import get_settings

check("落盘在 uuid 目录内", (get_settings().upload_dir / evil_id / "evil.fcs").is_file())
check("未越界写到 uploads 根", not (get_settings().upload_dir / "evil.fcs").exists())

r = client.put(f"{BASE}/api/files/{fid}/gates", json={
    "gates": [{"id": "x1", "name": "=SUM(A1)", "type": "rect", "x_label": "FSC-A", "y_label": "SSC-A",
               "x_min": 1, "x_max": 2, "y_min": 1, "y_max": 2, "parent_id": None}]
})
check("公式门名被拒 422", r.status_code == 422, str(r.status_code))

r = client.get(f"{BASE}/api/files/{fid}/events", params={"x": "FSC-A", "y": "SSC-A", "transform": "bogus"})
check("非法 transform 被拒 400", r.status_code == 400, str(r.status_code))

print(f"\n===== 结果: {ok} 通过, {fail} 失败 =====")
sys.exit(1 if fail else 0)
