"""散点图事件数据路由。"""

import numpy as np
from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import ApiError, EventsResponse
from app.services.sample_cache import get_sample

router = APIRouter(tags=["events"])

# sample 实例 id -> generate_transforms 结果（荧光通道为 Logicle，散射为 Linear）
_TRANSFORM_CACHE: dict[int, dict] = {}


def _get_transforms(sample):
    """获取（并缓存）sample 的通道变换表。"""
    key = id(sample)
    if key not in _TRANSFORM_CACHE:
        import flowkit as fk

        _TRANSFORM_CACHE[key] = fk.generate_transforms(sample)
    return _TRANSFORM_CACHE[key]


@router.get(
    "/files/{file_id}/events",
    response_model=EventsResponse,
    responses={404: {"model": ApiError}, 400: {"model": ApiError}},
)
def get_events(
    file_id: str,
    x: str = Query(..., description="X 轴通道标签"),
    y: str = Query(..., description="Y 轴通道标签"),
    limit: int = Query(20000, ge=100, le=100000, description="下采样点数上限"),
    compensate: bool = Query(
        True, description="文件含 $SPILLOVER 时默认应用补偿；传 false 看原始数据"
    ),
    transform: str = Query(
        "raw", description="显示空间：raw=线性（补偿后），logicle=logicle 显示变换"
    ),
) -> EventsResponse:
    """返回指定两通道的事件坐标（均匀下采样，保证可复现）。

    数据空间约定：所有数据（显示/门评估/统计/导出）默认在同一
    补偿线性空间；transform=logicle 仅影响本接口的显示坐标，
    门定义与 GatingML 导出始终使用补偿线性坐标。
    """
    if transform not in ("raw", "logicle"):
        raise HTTPException(status_code=400, detail="transform 仅支持 raw 或 logicle")

    try:
        sample = get_sample(file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    labels = list(sample.pnn_labels)
    if x not in labels or y not in labels:
        raise HTTPException(status_code=400, detail=f"通道不存在，可用通道: {', '.join(labels)}")

    has_comp = sample.compensation is not None
    source = "comp" if (compensate and has_comp) else "raw"
    events = sample.get_events(source=source)
    x_idx, y_idx = labels.index(x), labels.index(y)
    xs = np.asarray(events[:, x_idx], dtype=np.float64)
    ys = np.asarray(events[:, y_idx], dtype=np.float64)

    if transform == "logicle":
        transforms = _get_transforms(sample)
        for ch in (x, y):
            if ch not in transforms:
                raise HTTPException(status_code=400, detail=f"通道 {ch} 无可用的显示变换")
        xs = transforms[x].apply(xs)
        ys = transforms[y].apply(ys)

    total = events.shape[0]
    if total > limit:
        # 均匀抽样：等距取索引，首尾包含
        idx = np.linspace(0, total - 1, num=limit, dtype=np.int64)
        xs = xs[idx]
        ys = ys[idx]

    return EventsResponse(
        x_label=x,
        y_label=y,
        total_events=total,
        sampled=int(len(xs)),
        x=[float(v) for v in xs],
        y=[float(v) for v in ys],
        data_space="logicle" if transform == "logicle" else ("comp" if source == "comp" else "raw"),
        compensated=source == "comp",
    )
