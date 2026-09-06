"""Sample 实例缓存：避免对同一文件反复解析。

FlowKit 的 Sample 构造只读文件头（约 0.1s），事件数据按需加载；
缓存 Sample 实例可让门控评估、取数等操作复用已加载的事件。
"""

from flowkit import Sample

from ..core.config import get_settings
from .fcs_service import attach_compensation

# file_id -> Sample
_SAMPLE_CACHE: dict[str, Sample] = {}


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
        attach_compensation(sample)
        _SAMPLE_CACHE[file_id] = sample
    return sample


def drop_sample(file_id: str) -> None:
    """从缓存移除指定文件的 Sample（释放内存）。"""
    _SAMPLE_CACHE.pop(file_id, None)
