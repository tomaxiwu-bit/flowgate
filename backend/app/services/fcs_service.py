"""FlowKit 封装服务。

对上层（API 路由）暴露稳定的接口，屏蔽 FlowKit 的 API 细节，
方便后续替换实现或补充缓存/降采样逻辑。
"""

from __future__ import annotations

from pathlib import Path

from app.models.schemas import FcsSummary

# 常见散射光/时间参数名（用于区分荧光通道与非荧光参数）
_NON_FLUORESCENCE_PREFIXES = ("FSC-", "SSC-", "FSC", "SSC", "Time", "TIME")

# 单文件事件数上限（防护畸形 FCS 头构造的内存炸弹）
MAX_EVENTS = 5_000_000


class FcsParseError(Exception):
    """FCS 文件解析失败时抛出。"""


def _is_scatter_label(label: str) -> bool:
    """判断通道标签是否属于散射光/时间等非荧光参数。"""
    return label.startswith(_NON_FLUORESCENCE_PREFIXES)


def extract_spillover(sample) -> str | None:
    """从 Sample 元数据中提取 $SPILLOVER 补偿矩阵文本。

    FlowKit 的 Sample 构造时会读取 FCS header（含关键字表），
    这里直接复用其解析结果，避免二次读文件。
    """
    try:
        meta = sample.get_metadata()
    except Exception:
        return None
    if not meta:
        return None
    # FlowKit 元数据 key 可能为 "$SPILLOVER" 或小写 "spillover"
    for key in ("$SPILLOVER", "spillover", "$SPILL"):
        value = meta.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def attach_compensation(sample) -> bool:
    """若 FCS 内嵌 $SPILLOVER，则构造补偿矩阵并应用到 Sample。

    成功返回 True；无矩阵或构造失败返回 False（不抛异常，
    上层按"未补偿"继续处理，并通过 compensation_applied 字段
    把状态暴露给前端，避免静默降级）。
    """
    spill = extract_spillover(sample)
    if not spill:
        return False
    try:
        from flowkit import Matrix

        parts = spill.split(",")
        if len(parts) < 2:
            return False
        detector_count = int(parts[0])
        detectors = parts[1 : 1 + detector_count]
        if len(detectors) != detector_count:
            return False

        # GatingML 需要 fluorochrome 名：优先 $PnS（pns_labels），
        # 空串时用 detector 名兜底（保证导出 spectrumMatrix 非空）
        fluorochromes = []
        pns = list(getattr(sample, "pns_labels", None) or [])
        pnn = list(getattr(sample, "pnn_labels", None) or [])
        for det in detectors:
            fluoro = ""
            if det in pnn:
                idx = pnn.index(det)
                if idx < len(pns) and pns[idx]:
                    fluoro = pns[idx]
            fluorochromes.append(fluoro or det)

        matrix = Matrix(spill, detectors, fluorochromes=fluorochromes)
        sample.apply_compensation(matrix)
        return True
    except Exception:
        return False


def parse_fcs_file(path: Path, filename: str) -> FcsSummary:
    """解析 FCS 文件并返回摘要信息。

    Args:
        path: FCS 文件的磁盘路径。
        filename: 展示用文件名。

    Returns:
        FcsSummary：事件数、通道数、荧光/散射通道标签等。

    Raises:
        FcsParseError: FlowKit 无法解析该文件，或文件超出防护上限时抛出。
    """
    try:
        from flowkit import Sample
    except ImportError as exc:  # pragma: no cover - 依赖缺失时快速失败
        raise FcsParseError("FlowKit 未安装，请先执行 `uv sync`") from exc

    try:
        sample = Sample(str(path))
    except Exception as exc:
        raise FcsParseError(f"无法解析 FCS 文件 {filename!r}: {exc}") from exc

    # 兼容不同 FlowKit 版本：优先用 pnn_labels，回退到 pns_labels
    labels = list(getattr(sample, "pnn_labels", None) or getattr(sample, "pns_labels", []) or [])
    channel_count = int(getattr(sample, "channel_count", 0) or len(labels))
    event_count = int(getattr(sample, "event_count", 0) or 0)

    if not labels:
        # 最后兜底：从 measurements 的形状推导
        measurements = getattr(sample, "measurements", None)
        if measurements is not None and getattr(measurements, "ndim", 0) >= 2:
            channel_count = int(measurements.shape[1])
            event_count = int(measurements.shape[0])
        labels = [f"Ch{i + 1}" for i in range(channel_count)]

    # 防护畸形 FCS 头（$TOT/$PAR 虚高 → 内存炸弹）
    if event_count > MAX_EVENTS:
        raise FcsParseError(
            f"事件数 {event_count} 超过上限 {MAX_EVENTS}，拒绝解析（疑似畸形 FCS 头）"
        )

    scatter_labels = [label for label in labels if _is_scatter_label(label)]
    fluorescence_labels = [label for label in labels if label not in scatter_labels]

    # 尝试应用内嵌补偿并记录实际状态（与 has_spillover 分离）
    compensation_applied = attach_compensation(sample)

    return FcsSummary(
        filename=filename,
        event_count=event_count,
        channel_count=channel_count,
        channel_labels=fluorescence_labels,
        scatter_labels=scatter_labels,
        sample_id=getattr(sample, "sample_id", None) or None,
        has_spillover=extract_spillover(sample) is not None,
        compensation_applied=compensation_applied,
    )
