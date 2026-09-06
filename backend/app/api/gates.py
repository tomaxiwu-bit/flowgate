"""门控树存储与评估路由。"""

import json

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.core.config import get_settings
from app.models.schemas import ApiError, GateEvaluation, GatesPayload
from app.services.gate_service import evaluate_gates
from app.services.sample_cache import get_sample

router = APIRouter(tags=["gates"])


def _gates_path(file_id: str):
    return get_settings().gates_dir / f"{file_id}.json"


@router.get(
    "/files/{file_id}/gates",
    response_model=GatesPayload,
    responses={404: {"model": ApiError}},
)
def get_gates(file_id: str) -> GatesPayload:
    """读取已保存的门控树（不存在则返回空树）。"""
    path = _gates_path(file_id)
    if not path.exists():
        return GatesPayload(gates=[])
    try:
        return GatesPayload.model_validate_json(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValidationError):
        return GatesPayload(gates=[])


@router.put("/files/{file_id}/gates", response_model=GatesPayload)
def save_gates(file_id: str, payload: GatesPayload) -> GatesPayload:
    """保存门控树。"""
    path = _gates_path(file_id)
    path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    return payload


@router.post(
    "/files/{file_id}/gates/evaluate",
    response_model=list[GateEvaluation],
    responses={404: {"model": ApiError}, 400: {"model": ApiError}},
)
def evaluate(file_id: str, payload: GatesPayload) -> list[GateEvaluation]:
    """用 FlowKit 在真实事件上评估门控树，返回各门统计。"""
    try:
        sample = get_sample(file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        return evaluate_gates(sample, payload.gates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
