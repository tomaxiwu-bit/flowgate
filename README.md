# FlowGate

免费、开源、浏览器即用的流式细胞术（Flow Cytometry）数据 Web 分析工具。

> **Status: MVP 已完成** — FCS 解析、自动荧光补偿、交互散点图（线性 / Logicle 显示）、
> 拖放门控、层级门控树、统计导出与 GatingML 2.0 互操作均已可用。

> ⚠️ **部署安全警告**：本项目**无鉴权、无文件自动清理**，上传的文件会以明文落盘。
> **仅限本地 / 内网 / 可信环境使用，切勿直接暴露到公网。**

## 为什么做这个项目

商业流式分析软件（FlowJo、FCS Express）功能强大但昂贵，且授权绑定硬件；
Cytobank 提供 Web 分析但需要付费订阅。已有的开源 Web 方案（如 CAFE、AutoFlow）
以 R/Python 分析后端为主，**FlowGate 的差异化定位是**：

- **浏览器零安装 + 中文界面**：打开网址即用，不需要装 Python/R 或学习脚本；
- **GatingML 2.0 双向互操作**：门模板可导入 FlowJo / FCS Express 等商业软件；
- **补偿 + Logicle + 门控 + 统计全链路在浏览器内完成**（基于 FlowKit 领域内核）。

本项目瞄准学生、教学、小实验室与可复现性研究场景：
论文方法学可以光明正大引用、老师可以让全班同学点开一个网址、分析过程完全可审计。

## 核心功能

- [x] FCS 文件上传与解析（FlowKit）
- [x] **自动荧光补偿**（读取文件内嵌 `$SPILLOVER` 矩阵，线性模式默认应用）
- [x] **Logicle 显示变换**（查看模式；使用标准 Logicle 默认参数 w=0.5、m=4、T=通道 PnR，非数据自适应估计）
- [x] 交互式散点图（缩放 / 平移 / 框选放大）
- [x] 拖放门控（矩形门 / 多边形门）
- [x] 层级门控树（父子门 + 事件统计）
- [x] 群体统计导出（CSV，基于全量事件）
- [x] 图像导出（PNG）
- [x] GatingML 2.0 导入/导出（门模板可与 FlowJo / FCS Express 互操作）

## 数据空间约定（重要）

- **默认数据空间 = 补偿线性空间**：显示、门评估、统计与 GatingML 导出全部基于
  （已补偿的）线性坐标，保证内部自洽、可复现。
- `Logicle` 仅为**查看模式**：用于观察荧光数据分布（尤其负值拖尾），
  门控请在「线性」模式下进行；门定义与导出始终使用补偿线性坐标。
- 文件未内嵌 `$SPILLOVER` 时，线性模式即原始数据，接口 `compensated=false`。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Next.js (TypeScript, App Router) + 自研 Canvas 散点图组件 |
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
│   │   ├── core/           # 配置
│   │   ├── services/       # FlowKit 业务封装（解析、补偿、缓存、门控评估）
│   │   └── models/         # Pydantic 数据模型
│   ├── scripts/            # 工具脚本（e2e_check.py、verify_fcs.py 等）
│   └── tests/              # pytest 测试（37 项，覆盖率 89%）
├── frontend/               # Next.js 前端
│   └── components/         # ScatterPlot 等自研组件
├── examples/fcs/           # 公开测试 FCS 样本（FlowKit 官方 8 色数据集，含 $SPILLOVER）
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
| `GET /api/files/{id}/gatingml` | 导出 GatingML 2.0 XML |
| `POST /api/files/{id}/gatingml/import` | 导入 GatingML 2.0 XML |
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

> 注意：前端**直连**后端 API（默认 `http://127.0.0.1:8000`），不走 Next.js 代理
> ——Next.js 代理层有 10 MB 请求体上限，FCS 文件常超出。部署时通过
> `NEXT_PUBLIC_API_BASE_URL` 环境变量指定后端地址。

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

## 已知边界

- 门类型仅支持矩形门与多边形门；GatingML 导入会**跳过** Boolean / Quadrant 门
  （只导入矩形与多边形门）。
- GatingML 坐标基于补偿线性空间：若目标软件对同一文件应用了不同的补偿/变换，
  门坐标可能不重合，建议以"门模板"方式使用而非依赖自动对齐。
- Logicle 为查看模式，暂不支持在其空间内直接画门；散射通道（FSC/SSC/Time）
  在任何模式下均为线性显示。
- 补偿为"尽力而为"：文件内嵌 `$SPILLOVER` 但矩阵损坏或检测器名不匹配时，
  自动降级为未补偿数据，接口与界面会以 `uncompensated_fallback` 标记提示，
  不会静默产出错误统计。
- GatingML 导入在解析层拒绝任何 DOCTYPE（XXE 防护，含 UTF-16 编码场景）；
  畸形 XML 返回 400。
- 服务无鉴权、无上传文件自动清理：**请勿公网部署**（详见顶部警告）。

## 一键部署（Docker）

```powershell
docker compose up --build
# 前端 http://localhost:3000 · 后端 http://localhost:8000
```

数据持久化在 `flowgate-data` 卷（uploads / gates）。CI（.github/workflows/ci.yml）
在每次 push 时运行后端测试（覆盖率门槛 85%）与前端类型检查/构建。

## 开发排期（MVP，8 周）

| 周次 | 里程碑 | 状态 |
|---|---|---|
| 1-2 | FCS 解析 + 上传 | ✅ 完成 |
| 3-4 | 交互散点图 + 拖放门控 | ✅ 完成 |
| 5-6 | 层级门控树 + 群体统计 | ✅ 完成 |
| 7 | 统计导出 + GatingML 2.0 互操作 | ✅ 完成 |
| 8 | 测试、文档、部署、README | ✅ 完成 |
| 9 | 荧光补偿 + Logicle 显示 + 安全加固 | ✅ 完成 |
| 10 | CI、Docker、覆盖率门槛、XXE 加固、git 版本控制 | ✅ 完成 |
| 11 | 审计修复：缓存 LRU、DELETE API、补偿自包含导出、补偿降级告警、gating:id NCName、XXE 防护、荧光通道 E2E、Docker 远程部署 | ✅ 完成 |

## 发布路线（下一步）

- **上线在线 Demo**（免费，约 10 分钟）：[docs/DEPLOY_HUGGINGFACE_SPACES.md](./docs/DEPLOY_HUGGINGFACE_SPACES.md)
- **给上游 FlowKit 提 issue**（提升简历可写性）：[docs/FLOWKIT_ISSUE_DRAFT.md](./docs/FLOWKIT_ISSUE_DRAFT.md)
- 推 GitHub 后把仓库地址填进本 README 顶部与简历

## License

[MIT](./LICENSE)
