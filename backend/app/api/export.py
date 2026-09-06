"""导出/互操作路由：GatingML 2.0 与统计 CSV。"""

import csv
import io
import re

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.models.schemas import ApiError, GatesPayload
from app.services.gate_service import evaluate_gates
from app.services.gml_service import export_gatingml_xml, import_gatingml_xml
from app.services.sample_cache import get_sample

router = APIRouter(tags=["export"])

# CSV injection 防护：Excel/ LibreOffice 会将以下列首字符解析为公式
_CSV_DANGEROUS_PREFIX = re.compile(r"^[=+\-@\t\r\n]")


def _sanitize_csv_field(value: str) -> str:
    """净化 CSV 字符串字段，防公式注入。"""
    if _CSV_DANGEROUS_PREFIX.match(value):
        return "'" + value
    return value


def _load_gates(file_id: str) -> GatesPayload:
    """读取已保存的门控树，不存在则报错。"""
    from app.api.gates import _gates_path

    path = _gates_path(file_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="该文件还没有保存任何门控")
    return GatesPayload.model_validate_json(path.read_text(encoding="utf-8"))


@router.get(
    "/files/{file_id}/gatingml",
    responses={404: {"model": ApiError}, 400: {"model": ApiError}},
)
def export_gatingml(file_id: str) -> Response:
    """将门控树导出为 GatingML 2.0 XML 文件。"""
    try:
        payload = _load_gates(file_id)
        sample = get_sample(file_id)
        compensated = sample.compensation is not None
        xml_bytes = export_gatingml_xml(payload.gates, compensated=compensated)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="flowgate-{file_id[:8]}.xml"'
        },
    )


@router.post(
    "/files/{file_id}/gatingml/import",
    response_model=GatesPayload,
    responses={400: {"model": ApiError}},
)
async def import_gatingml(file_id: str, file: UploadFile = File(...)) -> GatesPayload:
    """从 GatingML 2.0 XML 文件导入门控树。"""
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="GatingML 文件超过 10 MB")
    try:
        return import_gatingml_xml(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/files/{file_id}/statistics.csv")
def export_statistics(file_id: str) -> Response:
    """导出门控树各门的统计为 CSV（基于全量事件评估）。"""
    try:
        payload = _load_gates(file_id)
        sample = get_sample(file_id)
        evaluations = evaluate_gates(sample, payload.gates)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["gate_id", "gate_name", "gate_type", "parent_id", "event_count", "absolute_percent", "relative_percent"]
    )
    by_id = {g.id: g for g in payload.gates}
    for ev in evaluations:
        gate = by_id.get(ev.id)
        writer.writerow(
            [
                ev.id,
                _sanitize_csv_field(ev.name),
                _sanitize_csv_field(gate.type if gate else ""),
                _sanitize_csv_field(gate.parent_id if gate and gate.parent_id else ""),
                ev.event_count,
                f"{ev.absolute_percent:.4f}",
                f"{ev.relative_percent:.4f}",
            ]
        )

    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="flowgate-{file_id[:8]}-statistics.csv"'},
    )
