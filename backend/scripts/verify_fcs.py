"""验证示例 FCS 文件能否被 FlowGate 后端解析。

用法（backend 目录下）:
    uv run python scripts/verify_fcs.py <path-to.fcs>
"""

import sys
from pathlib import Path

# 将 backend 根目录加入 sys.path，保证 `import app` 可用
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.fcs_service import FcsParseError, parse_fcs_file


def main() -> int:
    if len(sys.argv) != 2:
        print(f"用法: python {Path(__file__).name} <path-to.fcs>")
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"文件不存在: {path}")
        return 2

    try:
        summary = parse_fcs_file(path, path.name)
    except FcsParseError as exc:
        print(f"解析失败: {exc}")
        return 1

    print(f"文件名      : {summary.filename}")
    print(f"事件数      : {summary.event_count}")
    print(f"通道数      : {summary.channel_count}")
    print(f"荧光通道({len(summary.channel_labels)}): {', '.join(summary.channel_labels)}")
    print(f"散射/时间({len(summary.scatter_labels)}): {', '.join(summary.scatter_labels)}")
    if summary.sample_id:
        print(f"样本 ID     : {summary.sample_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
