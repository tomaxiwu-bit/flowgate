"""门控树评估服务。

把 FlowGate 前端定义的门控树（扁平数组 + parent_id）转换为
FlowKit Gate 对象，并在真实事件上按层级逐门计算统计。

实现说明：不依赖 FlowKit 的 GatingStrategy（其内部 anytree
根路径解析在新版本 anytree 下存在兼容问题），而是直接用
Gate.apply() 在 pandas DataFrame 上逐门过滤，层级语义
"子门只在父门内的事件上评估"由本模块显式实现。
"""

from collections import defaultdict

import numpy as np
import pandas as pd
from flowkit import Sample
from flowkit._models.dimension import Dimension
from flowkit._models.gates._gates import PolygonGate, RectangleGate

from ..models.schemas import GateDef, GateEvaluation


def _build_flowkit_gate(gate: GateDef) -> RectangleGate | PolygonGate:
    """将 FlowGate 门定义转换为 FlowKit Gate 对象。"""
    if gate.type == "rect":
        if gate.x_min is None or gate.x_max is None or gate.y_min is None or gate.y_max is None:
            raise ValueError(f"矩形门 {gate.id} 缺少范围")
        return RectangleGate(
            gate.id,
            [
                Dimension(gate.x_label, range_min=gate.x_min, range_max=gate.x_max),
                Dimension(gate.y_label, range_min=gate.y_min, range_max=gate.y_max),
            ],
        )
    if gate.type == "polygon":
        if len(gate.vertices) < 3:
            raise ValueError(f"多边形门 {gate.id} 至少需要 3 个顶点")
        return PolygonGate(
            gate.id,
            [Dimension(gate.x_label), Dimension(gate.y_label)],
            [(v[0], v[1]) for v in gate.vertices],
        )
    raise ValueError(f"不支持的门类型: {gate.type}")


def evaluate_gates(sample: Sample, gates: list[GateDef]) -> list[GateEvaluation]:
    """在 sample 上按层级应用门控树，返回每个门的统计。

    子门在父门事件子集上评估：relative_percent 相对父门事件数，
    absolute_percent 相对全部事件数。
    """
    if not gates:
        return []

    by_id = {g.id: g for g in gates}
    if len(by_id) != len(gates):
        raise ValueError("门 id 必须唯一")

    children: dict[str | None, list[GateDef]] = defaultdict(list)
    for gate in gates:
        children[gate.parent_id].append(gate)

    roots = children[None]
    if not roots:
        raise ValueError("门控树缺少根门（parent_id 为空的节点）")

    # 预检父门存在
    for gate in gates:
        if gate.parent_id is not None and gate.parent_id not in by_id:
            raise ValueError(f"门 {gate.id} 的父门不存在: {gate.parent_id}")

    df = _events_dataframe(sample)
    total = len(df)

    results: dict[str, dict[str, float | int]] = {}

    def process(gate: GateDef, parent_mask: np.ndarray | None) -> None:
        fk_gate = _build_flowkit_gate(gate)
        if parent_mask is None:
            mask = np.asarray(fk_gate.apply(df), dtype=bool)
        else:
            idx = np.where(parent_mask)[0]
            sub_mask = np.asarray(fk_gate.apply(df.loc[parent_mask]), dtype=bool)
            mask = np.zeros(total, dtype=bool)
            mask[idx[sub_mask]] = True

        count = int(mask.sum())
        parent_count = int(parent_mask.sum()) if parent_mask is not None else total
        results[gate.id] = {
            "count": count,
            "absolute_percent": (count / total * 100.0) if total else 0.0,
            "relative_percent": (count / parent_count * 100.0) if parent_count else 0.0,
        }
        for child in children[gate.id]:
            process(child, mask)

    for root in roots:
        process(root, None)

    evaluations: list[GateEvaluation] = []
    for gate in gates:
        stats = results[gate.id]
        evaluations.append(
            GateEvaluation(
                id=gate.id,
                name=gate.name,
                event_count=int(stats["count"]),
                absolute_percent=float(stats["absolute_percent"]),
                relative_percent=float(stats["relative_percent"]),
            )
        )
    return evaluations


# file_id -> DataFrame（事件 × 通道），与 Sample 缓存配套
_DF_CACHE: dict[str, pd.DataFrame] = {}


def _events_dataframe(sample: Sample) -> pd.DataFrame:
    """获取 sample 的事件 DataFrame（按 file_id 缓存）。

    若文件含补偿矩阵（sample.compensation 非 None），返回补偿后事件，
    保证显示、门评估与统计在同一数据空间。
    """
    from ..services.sample_cache import _SAMPLE_CACHE

    # 用 Sample 实例 id 定位缓存 key，避免耦合上传目录
    key = next((k for k, s in _SAMPLE_CACHE.items() if s is sample), id(sample))
    if key not in _DF_CACHE:
        source = "comp" if sample.compensation is not None else "raw"
        events = sample.get_events(source=source)
        _DF_CACHE[key] = pd.DataFrame(events, columns=list(sample.pnn_labels))
    return _DF_CACHE[key]
