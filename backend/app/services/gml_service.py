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
import re
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

# GatingML 的 gating:id 是 XML NCName：仅允许字母/数字/下划线/连字符，
# 且不能以数字开头。中文字符落在 XML 1.0 NameStartChar 区间内是合法的，
# 但空格、圆括号等必须替换。
_NCNAME_ILLEGAL = re.compile(r"[^\w\u4e00-\u9fff\-]")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _slug_id(name: str) -> str:
    """把门名转成合法的 GatingML gating:id（NCName）。

    显示名（中文/空格/括号）保留在门名中，这里仅生成 XML 安全的 id。
    """
    slug = _NCNAME_ILLEGAL.sub("_", name)
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        slug = "gate"
    if slug[0].isdigit():
        slug = "_" + slug
    return slug


def _unique_name(name: str, used: set[str]) -> str:
    """GatingML 要求门 ID 全局唯一，重名时追加后缀。"""
    base = _slug_id(name)
    if base not in used:
        used.add(base)
        return base
    i = 2
    while f"{base}-{i}" in used:
        i += 1
    candidate = f"{base}-{i}"
    used.add(candidate)
    return candidate


def export_gatingml_xml(gates: list[GateDef], sample=None) -> bytes:
    """将门控树导出为 GatingML 2.0 XML 字节串。

    Args:
        gates: 门控树。
        sample: 可选的 FlowKit Sample。若其已应用补偿（compensation 非 None），
            则把补偿矩阵写入 XML（spectrumMatrix）并让门坐标引用它，
            使导出的 GatingML 自包含；否则门坐标声明为 uncompensated。
    """
    if not gates:
        raise ValueError("门控树为空，无法导出")

    comp_ref = "uncompensated"
    if sample is not None and sample.compensation is not None:
        comp_ref = "spill"

    by_id = {g.id: g for g in gates}
    children: dict[str | None, list[GateDef]] = defaultdict(list)
    for gate in gates:
        children[gate.parent_id].append(gate)
    roots = children[None]
    if not roots:
        raise ValueError("门控树缺少根门")

    used_names: set[str] = set()
    strategy = GatingStrategy()

    if comp_ref == "spill":
        # 把补偿矩阵写入文档，门坐标的 compensation-ref 才能自洽（P1-N1）
        strategy.add_comp_matrix("spill", sample.compensation)

    added: set[str] = set()

    def add_recursive(gate: GateDef, ancestor_ids: list[str]) -> None:
        if gate.id in added:
            return
        # 构造 FlowKit Gate（GatingML id 用 NCName slug，保证 XML 合法）
        gate_id = _unique_name(gate.name or gate.id, used_names)
        if gate.type == "rect":
            if gate.x_min is None or gate.x_max is None or gate.y_min is None or gate.y_max is None:
                raise ValueError(f"矩形门 {gate.id} 缺少范围")
            fk_gate: RectangleGate | PolygonGate = RectangleGate(
                gate_id,
                [
                    Dimension(gate.x_label, compensation_ref=comp_ref, range_min=gate.x_min, range_max=gate.x_max),
                    Dimension(gate.y_label, compensation_ref=comp_ref, range_min=gate.y_min, range_max=gate.y_max),
                ],
            )
        elif gate.type == "polygon":
            if len(gate.vertices or []) < 3:
                raise ValueError(f"多边形门 {gate.id} 至少需要 3 个顶点")
            fk_gate = PolygonGate(
                gate_id,
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

        next_ancestors = ancestor_ids + [gate_id]
        for child in children[gate.id]:
            add_recursive(child, next_ancestors)

    for root in roots:
        add_recursive(root, [])

    buf = io.BytesIO()
    export_gatingml(strategy, buf)
    return buf.getvalue()


def _decode_xml_safely(data: bytes) -> str:
    """按 BOM/声明检测编码并解码，供 DOCTYPE 全文检查使用。

    支持 UTF-8 / UTF-16（LE/BE）；解码失败视为非法 XML。
    """
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="strict")
    if data[:3] == b"\xef\xbb\xbf":
        return data.decode("utf-8-sig", errors="strict")
    return data.decode("utf-8", errors="strict")


def import_gatingml_xml(xml_bytes: bytes) -> GatesPayload:
    """解析 GatingML 2.0 XML 为 FlowGate 门控树。

    仅支持矩形/多边形门；其他类型（布尔门、象限门等）会被跳过，
    门名作为显示名保留，内部 id 重新生成。

    XXE 防护（双层）：
    1. 解码后全文检查 DOCTYPE（无字节窗口限制，覆盖 UTF-16 编码）；
    2. lxml 安全解析器预检（resolve_entities=False / load_dtd=False /
       no_network=True），任何 DTD 声明都在解析层被拒绝。
    """
    from lxml import etree

    try:
        text = _decode_xml_safely(xml_bytes)
    except UnicodeDecodeError as exc:
        raise ValueError(f"GatingML 文件编码无法识别: {exc}") from exc

    if "<!DOCTYPE" in text.upper():
        raise ValueError("检测到 DOCTYPE 声明，已拒绝（XXE 防护）")

    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        recover=False,
    )
    try:
        etree.fromstring(xml_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"GatingML 文件无法解析: {exc}") from exc

    try:
        strategy = parse_gating_xml(io.BytesIO(xml_bytes))
    except Exception as exc:
        # 解析器差异等异常统一转业务错误（返回 400 而非 500）
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
