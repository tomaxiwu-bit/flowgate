#!/usr/bin/env python
"""FlowGate end-to-end verification.

Two independent paths, compared against each other:

1. HTTP path  : upload -> save gates -> evaluate -> export (real server, real API)
2. Local path : read the same FCS with FlowKit directly, apply the embedded
                $SPILLOVER matrix, mask the same coordinates (no app.* import)

If both agree, the numbers are recomputed from the file, not echoed by the API.

Usage:
    python tools/verify_e2e.py [--base http://127.0.0.1:8000] [--fcs <path>]

Exit code 0 = all checks passed. Non-zero = failure, details printed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FCS = REPO_ROOT / "examples" / "fcs" / "101_DEN084Y5_15_E01_008_clean.fcs"

BASE = "http://127.0.0.1:8000"

GATE1 = dict(x_min=60000, x_max=180000, y_min=20000, y_max=75000)
GATE2 = dict(x_min=60000, x_max=120000, y_min=20000, y_max=45000)

EXPECT_TOTAL = 290172
EXPECT_CHANNELS = 15
EXPECT_G1 = 179296
EXPECT_G1_ABS = 61.7896
EXPECT_G2 = 31589
EXPECT_G2_ABS = 10.8863
EXPECT_G2_REL = 17.6184
TOL = 0.02

_results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((ok, name, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  <- {detail}" if detail else ""))


def local_recount(fcs_path: Path) -> tuple[int, int, int]:
    import flowkit as fk

    sample = fk.Sample(str(fcs_path))
    pnn = list(sample.pnn_labels)
    meta = sample.get_metadata()
    spill = None
    for key in meta:
        if key.upper().lstrip("$") == "SPILLOVER":
            spill = meta[key]
            break
    if spill:
        parts = spill.split(",")
        n = int(parts[0])
        detectors = parts[1:1 + n]
        sample.apply_compensation(fk.Matrix(spill, detectors, fluorochromes=detectors))

    arr = np.asarray(sample.get_events(source="comp"))
    ix, iy = pnn.index("FSC-A"), pnn.index("SSC-A")
    g1 = (
        (arr[:, ix] >= GATE1["x_min"]) & (arr[:, ix] <= GATE1["x_max"])
        & (arr[:, iy] >= GATE1["y_min"]) & (arr[:, iy] <= GATE1["y_max"])
    )
    g2 = g1 & (arr[:, ix] <= GATE2["x_max"]) & (arr[:, iy] <= GATE2["y_max"])
    return int(arr.shape[0]), int(g1.sum()), int(g2.sum())


def main() -> int:
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--fcs", default=str(DEFAULT_FCS))
    args = ap.parse_args()
    BASE = args.base.rstrip("/")
    fcs = Path(args.fcs)

    if not fcs.exists():
        print(f"FCS not found: {fcs}")
        return 2

    try:
        import httpx
    except ImportError:
        print("need httpx: pip install httpx")
        return 2

    client = httpx.Client(base_url=BASE, timeout=180.0)

    # ---- 1. health
    try:
        r = client.get("/api/health")
        check("health 200 ok", r.status_code == 200 and r.json().get("status") == "ok", r.text[:120])
    except Exception as exc:  # noqa: BLE001
        check("health 200 ok", False, f"server unreachable: {exc}")
        print_summary()
        return 1

    # ---- 2. upload
    with fcs.open("rb") as fh:
        files = {"file": (fcs.name, fh, "application/octet-stream")}
        up = client.post("/api/files/upload", files=files)
    if up.status_code != 200:
        check("upload parses sample", False, f"HTTP {up.status_code}: {up.text[:200]}")
        print_summary()
        return 1
    body = up.json()
    file_id = body["file_id"]
    summary = body["summary"]
    check("upload parses sample", True, f"file_id={file_id}")
    check(
        "event_count == 290172",
        summary["event_count"] == EXPECT_TOTAL,
        f"got {summary['event_count']}",
    )
    check(
        "channel_count == 15",
        summary["channel_count"] == EXPECT_CHANNELS,
        f"got {summary['channel_count']}",
    )
    check(
        "spillover compensation applied",
        bool(summary["has_spillover"]) and bool(summary["compensation_applied"]),
        f"has_spillover={summary['has_spillover']} applied={summary['compensation_applied']}",
    )

    # ---- 3. gates
    payload = {
        "file_id": file_id,
        "gates": [
            {
                "id": "g1", "name": "gate_parent", "type": "rect",
                "x_label": "FSC-A", "y_label": "SSC-A",
                **GATE1, "parent_id": None, "vertices": [],
            },
            {
                "id": "g2", "name": "gate_child", "type": "rect",
                "x_label": "FSC-A", "y_label": "SSC-A",
                **GATE2, "parent_id": "g1", "vertices": [],
            },
        ],
    }
    put = client.put(f"/api/files/{file_id}/gates", json=payload)
    check("save 2 gates", put.status_code == 200 and len(put.json()["gates"]) == 2, f"HTTP {put.status_code}")

    # ---- 4. evaluate
    ev = client.post(f"/api/files/{file_id}/gates/evaluate", json=payload, timeout=180.0)
    if ev.status_code != 200:
        check("evaluate gates", False, f"HTTP {ev.status_code}: {ev.text[:200]}")
        print_summary()
        return 1
    rows = {row["id"]: row for row in ev.json()}
    g1, g2 = rows["g1"], rows["g2"]
    check("parent gate events == 179296", g1["event_count"] == EXPECT_G1, f"got {g1['event_count']}")
    check(
        "parent absolute_percent ~ 61.7896",
        abs(g1["absolute_percent"] - EXPECT_G1_ABS) <= TOL,
        f"got {g1['absolute_percent']}",
    )
    check("child gate events == 31589", g2["event_count"] == EXPECT_G2, f"got {g2['event_count']}")
    check(
        "child relative_percent ~ 17.6184",
        abs(g2["relative_percent"] - EXPECT_G2_REL) <= TOL,
        f"got {g2['relative_percent']}",
    )

    # ---- 5. exports
    csv = client.get(f"/api/files/{file_id}/statistics.csv")
    csv_text = csv.text
    header = csv_text.lstrip("\ufeff").splitlines()[0] if csv_text else ""
    check(
        "statistics.csv header + 2 rows",
        csv.status_code == 200
        and header.startswith("gate_id,gate_name")
        and len([ln for ln in csv_text.splitlines() if ln.strip()]) == 3,
        f"HTTP {csv.status_code}, lines={len(csv_text.splitlines())}",
    )

    xml = client.get(f"/api/files/{file_id}/gatingml")
    xml_text = xml.text
    check(
        "gatingml has ISAC v2.0 namespace",
        "http://www.isac-net.org/std/Gating-ML/v2.0/gating" in xml_text,
        f"{len(xml_text)} bytes",
    )
    check(
        "gatingml contains both gates",
        xml_text.count("<gating:RectangleGate") >= 2 or xml_text.count("<gating:PolygonGate") >= 2,
        "counting gate elements",
    )

    # ---- 6. independent local recount
    try:
        total, lg1, lg2 = local_recount(fcs)
        check("local total == API total", total == EXPECT_TOTAL, f"local {total}")
        check("local parent gate == API parent gate", lg1 == g1["event_count"], f"local {lg1} vs api {g1['event_count']}")
        check("local child gate == API child gate", lg2 == g2["event_count"], f"local {lg2} vs api {g2['event_count']}")
    except Exception as exc:  # noqa: BLE001
        check("independent FlowKit recount", False, f"{type(exc).__name__}: {exc}")

    print_summary()
    return 0 if all(ok for ok, _, _ in _results) else 1


def print_summary() -> None:
    ok = sum(1 for flag, _, _ in _results if flag)
    total = len(_results)
    print("\n" + "=" * 56)
    print(f"RESULT: {ok}/{total} checks passed")
    failed = [name for flag, name, _ in _results if not flag]
    if failed:
        print("FAILED: " + ", ".join(failed))
    print("=" * 56)


if __name__ == "__main__":
    sys.exit(main())
