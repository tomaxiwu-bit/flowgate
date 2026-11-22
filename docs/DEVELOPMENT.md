# 本地开发、API 与数据空间

[返回项目首页](../README.md)

以下命令均从项目根目录开始；前端与后端分别使用一个终端。

## 实现细节

- **补偿状态全链路透明**：`compensation_applied` / `uncompensated_fallback` 从后端到界面贯穿；
  文件含 `$SPILLOVER` 但矩阵损坏时**降级并明示**，绝不静默产出错误统计。
- **GatingML 2.0 自包含导出**：导出 XML 内嵌 `spectrumMatrix`（`compensation-ref="spill"`），
  不再依赖外部引用；门 id 按 NCName 规则生成（门名可含中文/空格，id 保持 XML 合法）。
- **安全加固**：XXE 双层防护（解码层 DOCTYPE 全文检查 + lxml 安全解析器，
  实测覆盖 UTF-16 编码与注释填充绕过）、路径遍历防护、CSV 公式注入防护、
  上传扩展名与大小校验、GatingML 导入畸形文件返回 400。
- **工程化**：pytest 与覆盖率门槛（CI 要求 85%）+
  两轮对抗式审计驱动修复；`evaluate_gates` 用 FlowKit 在真实事件上评估，
  荧光通道门控有专门的补偿显著性 E2E 测试。
- **性能**：LRU 有界缓存（sample / transform / DataFrame 三层联动）、
  `DELETE /api/files/{id}` 全量清理（内存 + 磁盘）、29 万事件散点抽样渲染。

## 数据空间约定（重要）

- **默认数据空间 = 补偿线性空间**：显示、门评估、统计与 GatingML 导出全部基于
  （已补偿的）线性坐标，保证内部自洽、可复现。
- `Logicle` 仅为**查看模式**：用于观察荧光数据分布（尤其负值拖尾），
  门控请在「线性」模式下进行；门定义与导出始终使用补偿线性坐标。
- 文件未内嵌 `$SPILLOVER` 时，线性模式即原始数据，接口 `compensated=false`。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Next.js 15 (TypeScript, App Router) + 自研 Canvas 散点图组件 |
| 后端 | FastAPI (Python 3.12) |
| 流式核心 | FlowKit（FCS 解析、补偿矩阵、Logicle 变换、门控评估） |
| 包管理 | uv (Python) / npm (Node) |

## 项目结构

```
flowgate/
├── backend/                # FastAPI 后端
│   ├── app/
│   │   ├── main.py         # 应用入口
│   │   ├── api/            # 路由（health / files / events / gates / export）
│   │   ├── core/           # 配置 + LRU 缓存
│   │   ├── services/       # FlowKit 业务封装（解析、补偿、缓存、门控评估、GatingML）
│   │   └── models/         # Pydantic 数据模型
│   └── tests/              # 后端测试与输入边界检查
├── frontend/               # Next.js 前端（upload / analyze 页面）
├── examples/fcs/           # 公开测试 FCS 样本（FlowKit 官方 8 色数据集，含 $SPILLOVER）
├── examples/gatingml/      # 官方 GatingML 2.0 样例（8_color_ICS.xml）
├── docs/                   # 部署指南、FlowKit issue 草稿
└── README.md
```

## API 一览

| 端点 | 说明 |
|---|---|
| `GET /api/health` | 健康检查 |
| `POST /api/files/upload` | 上传并解析 FCS（≤500 MB，含 `$SPILLOVER` 自动补偿） |
| `GET /api/files/{id}` | 文件解析摘要（含 `has_spillover` / `compensation_applied`） |
| `DELETE /api/files/{id}` | 删除文件：清缓存、删数据目录与门控文件 |
| `GET /api/files/{id}/events?x=&y=&limit=&compensate=&transform=` | 两通道事件坐标；`transform=raw\|logicle` |
| `GET /api/files/{id}/gates` | 读取门控树 |
| `PUT /api/files/{id}/gates` | 保存门控树（门名白名单校验） |
| `POST /api/files/{id}/gates/evaluate` | 用 FlowKit 在真实事件上评估各门统计 |
| `GET /api/files/{id}/gatingml` | 导出 GatingML 2.0 XML（自包含补偿矩阵） |
| `POST /api/files/{id}/gatingml/import` | 导入 GatingML 2.0 XML（XXE 防护） |
| `GET /api/files/{id}/statistics.csv` | 导出各门统计 CSV（全量事件，防公式注入） |

## 示例数据

`examples/fcs/` 提供公开测试样本（来自 FlowKit 官方仓库的 8 色 ICS 数据集，
15 通道 / 29 万事件，约 17 MB，**内嵌 8×8 真实 `$SPILLOVER` 补偿矩阵**）；
`examples/gatingml/` 提供配套的官方 GatingML 2.0 文件（`8_color_ICS.xml`，
含层级多边形门，用于导入测试）。验证后端解析：

```powershell
cd backend
uv run python scripts/verify_fcs.py "../examples/fcs/101_DEN084Y5_15_E01_008_clean.fcs"
```

## 快速开始

### 后端

```powershell
cd backend
uv sync          # 创建虚拟环境并安装依赖
uv run uvicorn app.main:app --reload --port 8000
```

### 前端

```powershell
cd frontend
npm install
npm run dev     # 默认 http://localhost:3000
```

> 前端通过 Next.js `/api/*` 代理转发到后端（`next.config.ts` 的 rewrites）；
> 后端地址可用 `NEXT_PUBLIC_API_BASE_URL` 环境变量覆盖（本地默认
> `http://127.0.0.1:8000`，Docker/远程部署时注入实际地址）。

## 使用流程

1. 打开 `http://localhost:3000/upload`，上传一个 FCS 文件（可用 `examples/fcs/` 里的示例）；
2. 上传成功后点击「进入分析」；含 `$SPILLOVER` 的文件会自动应用荧光补偿；
3. 在散点图上选择工具：`平移` / `框选缩放` / `矩形门` / `多边形门`；
4. 需要观察荧光分布（负值拖尾等）时，切到「显示变换 → Logicle」查看；
   门控请切回「线性」模式进行；
5. 画门后自动评估并持久化；点击门控树中的门可选中（高亮门内事件、显示占比），
   选中后新建的门会作为其子门（层级门控）；
6. 导出 / 互操作：`GatingML 导出`（可作为门模板导入 FlowJo / FCS Express）、
   `统计 CSV`、`图像 PNG`、`导入 GatingML`（可用 `examples/gatingml/8_color_ICS.xml` 演示）。

## 已知边界（诚实清单）

- 门类型仅支持矩形门与多边形门；GatingML 导入会**跳过** Boolean / Quadrant 门。
- GatingML 坐标基于补偿线性空间：若目标软件对同一文件应用了不同的补偿/变换，
  门坐标可能不重合，建议以"门模板"方式使用。
- Logicle 为查看模式，暂不支持在其空间内直接画门；散射通道（FSC/SSC/Time）
  在任何模式下均为线性显示。
- 补偿为"尽力而为"：`$SPILLOVER` 损坏或检测器名不匹配时自动降级为未补偿数据，
  界面与接口以 `uncompensated_fallback` 标记提示。
- GatingML 导入在解析层拒绝任何 DOCTYPE（XXE 防护，含 UTF-16 编码场景）。
- 服务无鉴权、无上传文件自动清理：**请勿公网部署**。
- 尚未实现：Boolean / Quadrant 门、直方图、批量分析、撤销重做（已在路线图评估）。


## 工程与质量

- pytest 与覆盖率检查（CI 门槛 85%）覆盖解析、补偿、缓存淘汰、上传边界、
  XXE（UTF-8/UTF-16/注释填充）、GatingML 双向、荧光通道门控显著性、DELETE 清理。
- 两轮对抗式审计（含安全与推销演练）驱动修复，审计报告与修复记录见 git 历史。
- 上游：核心能力基于 [FlowKit](https://github.com/whitews/flowkit)；
  发现的文档/API 改进点见 [docs/FLOWKIT_ISSUE_DRAFT.md](.././docs/FLOWKIT_ISSUE_DRAFT.md)。
