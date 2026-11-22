# FlowGate · 流式细胞术分析工作台

在浏览器中完成 **FCS 上传、荧光补偿、交互门控和群体统计导出**。适合教学演示、小实验室的单文件分析，以及需要保留门模板的研究流程。

*Self-hosted FCS analysis with compensation, interactive gates and exports.*

**[启动并试用](#启动并试用)** · [公开 FCS 样例](examples/fcs/) · [示例门模板](examples/gatingml/8_color_ICS.xml) · [开发与 API](docs/DEVELOPMENT.md)

[![CI](https://github.com/tomaxiwu-bit/flowgate/actions/workflows/ci.yml/badge.svg)](https://github.com/tomaxiwu-bit/flowgate/actions/workflows/ci.yml)

FlowGate 需要先在本机或可信环境部署。部署后，使用者通过浏览器操作，无需编写分析脚本；也提供维护者按需开启的临时公网实例（见下节）。

## 一份 FCS 可以怎样分析

```mermaid
flowchart LR
    A["上传 FCS"] --> B["检查通道与补偿状态"]
    B --> C["选择坐标并画门"]
    C --> D["查看父子群体与占比"]
    D --> E["导出 CSV / PNG / GatingML"]
```

| 分析环节 | 当前能力 | 你能核查什么 |
|---|---|---|
| 读取数据 | 解析 FCS，检查文件内嵌 `$SPILLOVER` | 通道、事件数与补偿是否实际应用 |
| 观察分布 | Canvas 散点图，线性 / Logicle 显示 | 补偿后负值与荧光分布 |
| 划分群体 | 矩形门、多边形门与父子门树 | 门内事件和群体占比 |
| 保存结果 | 全量事件统计 CSV、PNG、GatingML 2.0 子集 | 统计数值与可交换的门模板 |

仓库附带 FlowKit 公开的 **8 色 ICS 样例，约 29 万事件**，以及配套门模板，可用于走通一次完整流程。图上的抽样显示与统计导出采用的全量事件应区分阅读。

## 在线试用（临时实例）

维护者本机正在运行的实例，经 Cloudflare 隧道转发：

<https://nutten-tutorials-move-rank.trycloudflare.com>

打开后上传 `examples/fcs/101_DEN084Y5_15_E01_008_clean.fcs`（约 17 MB），即可完整走一遍"上传 → 补偿状态 → 画门 → 占比 → 导出"。几点如实说明：

- 这是从维护者电脑转发出来的临时隧道，**地址随进程重启变化**，本机关机即失效；失效请按下节自建。
- 实例没有登录与鉴权，上传的文件只存在该进程内存与临时目录，不要传敏感数据。
- 17 MB 样例经隧道上传约需 20–40 秒，取决于维护者上行带宽。

## 启动并试用

推荐从 Docker 启动。需要 Git 和可运行 Docker Compose 的环境：

```powershell
git clone https://github.com/tomaxiwu-bit/flowgate.git
Set-Location flowgate
docker compose up --build
```

打开 <http://localhost:3000/upload>。首次构建需要下载依赖，之后按下面步骤使用：

1. 上传 `examples/fcs/101_DEN084Y5_15_E01_008_clean.fcs`。
2. 进入分析，先查看通道和补偿状态。文件内的补偿矩阵不可用时，界面会明确提示回退到未补偿数据。
3. 选择坐标；在**线性模式**画矩形门或多边形门。选中已有门后，新门会作为它的子门。
4. 查看门内事件与占比，再导出统计 CSV、图像 PNG 或 GatingML 模板。也可导入 `examples/gatingml/8_color_ICS.xml`。

不使用 Docker 时，按 [本地开发指南](docs/DEVELOPMENT.md) 分别启动 Python 3.12 后端和 Next.js 前端。后端健康检查位于 <http://localhost:8000/api/health>。

## 使用前需要知道

**当前是无账号体系的本地 / 可信环境工具。** 上传文件会保存到服务端，尚无自动清理或多用户隔离；默认 Docker 端口只绑定本机。需要远程共享时，应先补访问控制并确认文件管理方式。

门控与导出采用补偿线性坐标；Logicle 用于查看，暂不支持在其空间内直接画门。GatingML 当前支持矩形门和多边形门，Boolean / Quadrant 门会被跳过。与其他软件交换模板时，须核对所用补偿、变换与坐标约定。

尚未提供直方图、批量分析、门控撤销 / 重做。当前范围与接口细节见 [开发参考](docs/DEVELOPMENT.md)。

## 代码与文档

| 位置 | 内容 |
|---|---|
| `frontend/` | Next.js + TypeScript，上传、散点图与门控界面 |
| `backend/` | FastAPI + FlowKit，解析、补偿、门评估与导出 |
| `examples/` | 可供试用的公开 FCS 与 GatingML 文件 |
| [开发参考](docs/DEVELOPMENT.md) | 本地启动、数据空间、API、已知边界 |
| [部署说明](docs/DEPLOY_HUGGINGFACE_SPACES.md) | 容器构建参考；部署前仍需满足访问控制要求 |

CI 执行后端测试、覆盖率门槛和前端检查；当前状态见上方 CI 链接。问题反馈请附软件版本、补偿状态和复现步骤，并优先使用仓库公开样例描述问题。

代码采用 [MIT](LICENSE)。FCS 解析与门评估基于 [FlowKit](https://github.com/whitews/flowkit)。
