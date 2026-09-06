"""GatingML 2.0 互操作服务。

导出：把 FlowGate 门控树（扁平数组 + parent_id）转换为标准
GatingML 2.0 XML（通过 FlowKit 的 export_gatingml）。
导入：解析标准 GatingML 2.0 XML，转换为 FlowGate 门控树
（通过 FlowKit 的 parse_gating_xml）。

说明：FlowKit 的 GatingStrategy 在 anytree 2.13 下对根门路径
`()` 的解析有兼容问题（它期望 `('root',)`），因此本服务在
构造策略时统一使用 `('root',)` 作为根路径。
"""

import io
import uuid
from collections import defaultdict

from flowkit import export_gatingml, parse_gating_xml
from flowkit._models.dimension import Dimension
from flowkit._models.gates._gates import PolygonGate, RectangleGate
from flowkit._models.gating_strategy import GatingStrategy

from ..models.schemas import GateDef, GatesPayload

_ROOT_PATH = ("root",)

# 可导入的门类型（FlowKit Gate.gate_type）
_SUPPORTED_TYPES = {"RectangleGate", "PolygonGate"}


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _unique_name(name: str, used: set[str]) -> str:
    """GatingML 要求门 ID 全局唯一，重名时追加后缀。"""
    if name not in used:
        used.add(name)
        return name
    i = 2
    while f"{name}-{i}" in used:
        i += 1
    candidate = f"{name}-{i}"
    used.add(candidate)
    return candidate


def export_gatingml_xml(gates: list[GateDef], compensated: bool = False) -> bytes:
    """将门控树导出为 GatingML 2.0 XML 字节串。

    Args:
        gates: 门控树。
        compensated: 数据是否已应用 FCS 内嵌补偿（$SPILLOVER）。
            为 True 时门坐标声明为"FCS 补偿空间"（compensation-ref="FCS"），
            目标软件加载同一文件的内嵌矩阵后坐标即对齐。
    """
    if not gates:
        raise ValueError("门控树为空，无法导出")

    comp_ref = "FCS" if compensated else "uncompensated"

    by_id = {g.id: g for g in gates}
    children: dict[str | None, list[GateDef]] = defaultdict(list)
    for gate in gates:
        children[gate.parent_id].append(gate)
    roots = children[None]
    if not roots:
        raise ValueError("门控树缺少根门")

    used_names: set[str] = set()
    strategy = GatingStrategy()
    added: set[str] = set()

    def add_recursive(gate: GateDef, ancestor_ids: list[str]) -> None:
        if gate.id in added:
            return
        # 构造 FlowKit Gate（门名用去重后的 GatingML ID）
        gate_name = _unique_name(gate.name or gate.id, used_names)
        if gate.type == "rect":
            if gate.x_min is None or gate.x_max is None or gate.y_min is None or gate.y_max is None:
                raise ValueError(f"矩形门 {gate.id} 缺少范围")
            fk_gate: RectangleGate | PolygonGate = RectangleGate(
                gate_name,
                [
                    Dimension(gate.x_label, compensation_ref=comp_ref, range_min=gate.x_min, range_max=gate.x_max),
                    Dimension(gate.y_label, compensation_ref=comp_ref, range_min=gate.y_min, range_max=gate.y_max),
                ],
            )
        elif gate.type == "polygon":
            if len(gate.vertices or []) < 3:
                raise ValueError(f"多边形门 {gate.id} 至少需要 3 个顶点")
            fk_gate = PolygonGate(
                gate_name,
                [
                    Dimension(gate.x_label, compensation_ref=comp_ref),
                    Dimension(gate.y_label, compensation_ref=comp_ref),
                ],
                [(v[0], v[1]) for v in gate.vertices],
            )
        else:
            raise ValueError(f"不支持的门类型: {gate.type}")

        # FlowKit 的 gate_path 必须从 root 开始（根门为 ('root',)）
        path = _ROOT_PATH + tuple(ancestor_ids)
        strategy.add_gate(fk_gate, gate_path=path)
        added.add(gate.id)

        next_ancestors = ancestor_ids + [gate_name]
        for child in children[gate.id]:
            add_recursive(child, next_ancestors)

    for root in roots:
        add_recursive(root, [])

    buf = io.BytesIO()
    export_gatingml(strategy, buf)
    return buf.getvalue()


def import_gatingml_xml(xml_bytes: bytes) -> GatesPayload:
    """解析 GatingML 2.0 XML 为 FlowGate 门控树。

    仅支持矩形/多边形门；其他类型（布尔门、象限门等）会被跳过，
    门名作为显示名保留，内部 id 重新生成。
    """
    try:
        strategy = parse_gating_xml(io.BytesIO(xml_bytes))
    except ValueError as exc:
        raise ValueError(f"GatingML 文件无法解析: {exc}") from exc

    gates: list[GateDef] = []
    for gate_name, gate_path in strategy.get_gate_ids():
        path = list(gate_path)
        # path 形如 ('root', '父门', ...)；排除 'root'
        ancestors = path[1:]
        if len(ancestors) > 0:
            parent_name = ancestors[-1]
        else:
            parent_name = None

        try:
            gate = strategy.get_gate(gate_name, gate_path)
        except Exception:  # noqa: BLE001 - 跳过无法读取的门
            continue
        if gate.gate_type not in _SUPPORTED_TYPES:
            continue

        dims = gate.dimensions
        if len(dims) != 2:
            continue
        x_dim, y_dim = dims[0], dims[1]

        if gate.gate_type == "RectangleGate":
            if x_dim.min is None or x_dim.max is None or y_dim.min is None or y_dim.max is None:
                continue
            gate_def = GateDef(
                id=_new_id(),
                name=gate_name,
                type="rect",
                x_label=x_dim.id,
                y_label=y_dim.id,
                x_min=x_dim.min,
                x_max=x_dim.max,
                y_min=y_dim.min,
                y_max=y_dim.max,
                parent_id=None,
            )
        else:
            gate_def = GateDef(
                id=_new_id(),
                name=gate_name,
                type="polygon",
                x_label=x_dim.id,
                y_label=y_dim.id,
                vertices=[[float(v[0]), float(v[1])] for v in gate.vertices],
                parent_id=None,
            )

        # 通过门名建立 parent_id 关联
        if parent_name is not None:
            parent = next((g for g in gates if g.name == parent_name), None)
            if parent is not None:
                gate_def.parent_id = parent.id
        gates.append(gate_def)

    return GatesPayload(gates=gates)
