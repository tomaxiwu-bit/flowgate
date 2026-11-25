# FlowGate 验证与复现

[项目首页](README.md) · [本地开发与 API](docs/DEVELOPMENT.md)

使用仓库附带的公开 FCS 样例，比较 HTTP 分析链路与直接使用 FlowKit 的本地计数，并核对统计与门模板导出。本文件提供操作步骤及历史基准，便于独立检查结果来源。

## 先准备本地服务

需要 Python 3.12、uv，以及前端开发所需的 Node.js 和 npm。获取完整仓库后，在 `flowgate/` 根目录打开终端。

终端一，安装后端及验证依赖并启动 API：

```powershell
Set-Location backend
uv sync --locked --group dev
uv run --locked --group dev uvicorn app.main:app --host 127.0.0.1 --port 8000
```

验证脚本使用的 httpx 包在后端开发依赖中。需要查看浏览器界面时，在另一个从项目根目录打开的终端启动前端：

```powershell
Set-Location frontend
npm ci
npm run dev
```

后端健康检查为 <http://127.0.0.1:8000/api/health>，前端上传页为 <http://localhost:3000/upload>。完整部署方式与当前演示入口见 [README](README.md)。

## 运行固定样例检查

保持后端运行，在第三个终端回到项目根目录执行：

```powershell
.\backend\.venv\Scripts\python.exe tools/verify_e2e.py
```

也可以显式指定已启动的服务：

```powershell
.\backend\.venv\Scripts\python.exe tools/verify_e2e.py --base http://127.0.0.1:8000
```

脚本会上传公开样例并写入测试门数据，请确认 `--base` 指向预期服务。默认读取 `examples/fcs/101_DEN084Y5_15_E01_008_clean.fcs`，预期计数也绑定这份文件；更换输入时需要重新确认基准。

退出码 0 表示本次脚本检查通过；非零时应阅读具体失败项。2026-11-25 本次文档维护没有启动服务或重跑该脚本，下面保留的是原文档中的 2026-11-20 历史结果。

## 历史结果与核对范围

原记录为 16/16 项检查通过，关键数值如下：

| 项目 | 固定样例基准 |
|---|---:|
| 总事件 | 290,172 |
| 通道数 | 15 |
| 父门事件 | 179,296 |
| 父门占全样本 | 61.7896% |
| 子门事件 | 31,589 |
| 子门占父门 | 17.6184% |
| 子门占全样本 | 10.8863% |

检查包括三部分：

1. **HTTP 分析链路**：上传、解析、保存两级门、评估、导出 CSV 与 GatingML。
2. **本地重算**：直接使用 FlowKit 读取同一文件和内嵌补偿矩阵，以相同坐标计算事件掩码；不导入应用的 `app.*` 模块。
3. **导出结构**：检查 CSV 表头与行数、GatingML 2.0 命名空间与门元素。

这些检查提供针对固定样例的实现一致性证据，没有完成与 FlowJo 等软件的独立对照，也不能替代实验设计与门控判断的复核。

## 常见检查点

- 在浏览器画门时切回线性模式；Logicle 当前用于查看。
- 核对界面的补偿状态。补偿矩阵损坏或检测器名不匹配时，程序会提示未补偿回退。
- pytest 无法创建临时目录时，可从后端目录指定一个尚不存在的专用目录：`uv run --locked --group dev pytest -q --basetemp .pytest-tmp-unique`。pytest 会管理该目录，不要指向已有数据目录。
- 页面返回 404/500 时先查看前端终端日志，确认构建完成且没有多个开发服务共用同一构建目录，再按开发指南重新启动。
- 本地 API 与公网演示是不同运行环境；公网实例的资源、冷启动和文件保存范围见首页。解析耗时及历史测试数不应当作每次运行的保证。
