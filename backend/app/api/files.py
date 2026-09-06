"""FCS 文件上传与元信息路由。"""

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import get_settings
from app.models.schemas import ApiError, FcsSummary, FileUploadResponse
from app.services.fcs_service import FcsParseError, parse_fcs_file
from app.services.sample_cache import get_sample, _resolve_fcs_path

router = APIRouter(tags=["files"])

_ALLOWED_EXTENSIONS = {".fcs"}


@router.get(
    "/files/{file_id}",
    response_model=FcsSummary,
    responses={404: {"model": ApiError}},
)
def get_file_meta(file_id: str) -> FcsSummary:
    """返回已上传文件的解析摘要。"""
    try:
        path = _resolve_fcs_path(file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        # 已缓存时直接复用，未缓存时用现有解析函数
        return parse_fcs_file(Path(path), Path(path).name)
    except FcsParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/files/upload",
    response_model=FileUploadResponse,
    responses={400: {"model": ApiError}, 413: {"model": ApiError}},
)
async def upload_fcs(file: UploadFile = File(...)) -> FileUploadResponse:
    """上传并解析一个 FCS 文件。

    校验扩展名与大小后保存到临时目录，用 FlowKit 解析并返回摘要。
    """
    settings = get_settings()

    original_name = Path(file.filename or "unnamed.fcs").name or "unnamed.fcs"
    ext = Path(original_name).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"仅支持 FCS 文件，收到扩展名 {ext!r}")

    # 流式写入，避免大文件直接读入内存
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过大小上限 {settings.max_upload_mb} MB",
        )

    file_id = uuid.uuid4().hex
    dest_dir = settings.upload_dir / file_id
    dest_dir.mkdir(parents=True, exist_ok=False)
    dest_path = dest_dir / original_name

    try:
        dest_path.write_bytes(content)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"保存文件失败: {exc}") from exc

    try:
        summary = parse_fcs_file(dest_path, original_name)
    except FcsParseError as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileUploadResponse(file_id=file_id, summary=summary)
