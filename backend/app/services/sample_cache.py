"""Sample 实例缓存：避免对同一文件反复解析。

FlowKit 的 Sample 构造只读文件头（约 0.1s），事件数据按需加载；
缓存 Sample 实例可让门控评估、取数等操作复用已加载的事件。

缓存均为有界 LRU（maxsize=10），防止无界增长导致内存耗尽
（对应审计 P0-N1：三处缓存无界泄漏）。
"""

from flowkit import Sample

from ..core.config import get_settings
from ..core.lru import LRUCache
from .fcs_service import attach_compensation

# file_id -> Sample（有界 LRU）
_SAMPLE_CACHE: LRUCache[str, Sample] = LRUCache(maxsize=10)

# file_id -> generate_transforms 结果（荧光通道 Logicle / 散射 Linear）
_TRANSFORM_CACHE: LRUCache[str, dict] = LRUCache(maxsize=10)

# file_id -> 补偿是否成功应用（True=已补偿，False=无矩阵或补偿失败）
_COMPENSATION_STATE: dict[str, bool] = {}


def _resolve_fcs_path(file_id: str) -> str:
    """在 uploads/<file_id>/ 下定位唯一的 .fcs 文件。"""
    upload_dir = get_settings().upload_dir / file_id
    if not upload_dir.is_dir():
        raise FileNotFoundError(f"文件不存在: {file_id}")
    fcs_files = sorted(upload_dir.glob("*.fcs"))
    if not fcs_files:
        raise FileNotFoundError(f"文件不存在: {file_id}")
    return str(fcs_files[0])


def get_sample(file_id: str) -> Sample:
    """获取（或加载并缓存）指定文件的 Sample 实例。

    若 FCS 内嵌 $SPILLOVER 补偿矩阵，加载后自动应用补偿，
    后续 get_events(source="comp") 返回补偿后数据。
    """
    sample = _SAMPLE_CACHE.get(file_id)
    if sample is None:
        sample = Sample(_resolve_fcs_path(file_id))
        comp_ok = attach_compensation(sample)
        _COMPENSATION_STATE[file_id] = comp_ok
        _SAMPLE_CACHE.put(file_id, sample)
    return sample


def get_transforms(file_id: str, sample: Sample) -> dict:
    """获取（并缓存）sample 的通道变换表（key 为 file_id，随 Sample 淘汰）。"""
    transforms = _TRANSFORM_CACHE.get(file_id)
    if transforms is None:
        import flowkit as fk

        transforms = fk.generate_transforms(sample)
        _TRANSFORM_CACHE.put(file_id, transforms)
    return transforms


def get_compensation_state(file_id: str) -> bool:
    """文件是否已成功应用补偿（False=无 $SPILLOVER 或补偿失败）。"""
    return _COMPENSATION_STATE.get(file_id, False)


def has_spillover(file_id: str) -> bool:
    """文件是否内嵌 $SPILLOVER 矩阵文本（与是否补偿成功无关）。"""
    from .fcs_service import extract_spillover

    sample = _SAMPLE_CACHE.get(file_id)
    if sample is None:
        try:
            sample = Sample(_resolve_fcs_path(file_id))
        except (FileNotFoundError, Exception):  # noqa: BLE001 - 元信息不可得时视为无
            return False
    return extract_spillover(sample) is not None


def evict(file_id: str) -> None:
    """仅清内存缓存（不删磁盘数据），供测试与内部逻辑使用。"""
    _SAMPLE_CACHE.pop(file_id)
    _TRANSFORM_CACHE.pop(file_id)
    _COMPENSATION_STATE.pop(file_id, None)

    from app.services.gate_service import drop_dataframe

    drop_dataframe(file_id)


def drop_sample(file_id: str) -> None:
    """从所有缓存移除指定文件，并删除其数据目录与门控文件。"""
    evict(file_id)

    # 删除磁盘数据：uploads/<file_id>/ 与 gates/<file_id>.json
    settings = get_settings()
    import shutil

    upload_dir = settings.upload_dir / file_id
    if upload_dir.is_dir():
        shutil.rmtree(upload_dir, ignore_errors=True)
    gates_file = settings.gates_dir / f"{file_id}.json"
    if gates_file.exists():
        gates_file.unlink(missing_ok=True)
