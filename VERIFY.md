# 验证 FlowGate：给 CODEX 的任务说明

这份文档只有一个目的：让一个**没有上下文**的代理或人，能在 3 分钟内判断
「flowgate 到底是真工具，还是 AI 画的空壳」。

## 通道地址

| 通道 | 地址 | 说明 |
|---|---|---|
| 后端 API | `http://127.0.0.1:8000/api` | FastAPI，OpenAPI 在 `/openapi.json` |
| 前端页面 | `http://localhost:3000` | Next.js，上传/分析页可用 |
| 一键验证 | `python tools/verify_e2e.py` | 16 项断言，退出码 0 = 全过 |

服务由本机 PowerShell 启动，命令见文末「怎么起服务」。

## 一条命令

```powershell
# 后端 venv 里跑，工作目录随意
& "C:\Users\18519\OneDrive\桌面\github项目\flowgate\backend\.venv\Scripts\python.exe" `
  "C:\Users\18519\OneDrive\桌面\github项目\flowgate\tools\verify_e2e.py"
```

期望输出（2026-11-20 实测原文，16/16）：

```
[PASS] health 200 ok  <- {"status":"ok","version":"0.1.0"}
[PASS] upload parses sample  <- file_id=8d41a8c3b13c4f8aa2546f2656b40f21
[PASS] event_count == 290172  <- got 290172
[PASS] channel_count == 15  <- got 15
[PASS] spillover compensation applied  <- has_spillover=True applied=True
[PASS] save 2 gates  <- HTTP 200
[PASS] parent gate events == 179296  <- got 179296
[PASS] parent absolute_percent ~ 61.7896  <- got 61.78955929586591
[PASS] child gate events == 31589  <- got 31589
[PASS] child relative_percent ~ 17.6184  <- got 17.618351775834373
[PASS] statistics.csv header + 2 rows  <- HTTP 200, lines=3
[PASS] gatingml has ISAC v2.0 namespace  <- 6812 bytes
[PASS] gatingml contains both gates  <- counting gate elements
[PASS] local total == API total  <- local 290172
[PASS] local parent gate == API parent gate  <- local 179296 vs api 179296
[PASS] local child gate == API child gate  <- local 31589 vs api 31589

========================================================
RESULT: 16/16 checks passed
========================================================
```

## 这个脚本在验什么（三条独立证据链）

1. **HTTP 全链路**：上传 → 解析 → 存门 → 在真实事件上评估 → 导出 CSV / GatingML。
   断言的是具体数字，不是「返回 200」这种敷衍检查。
2. **绕过 API 的本地重算**：脚本自己用 FlowKit 打开同一个 FCS，读文件内嵌
   `$SPILLOVER`、构造补偿矩阵、用同一组坐标做 mask 计数，**完全不 import `app.*`**。
   两条路径必须给出同一个 179296 / 31589。如果后端是假的，这条会立刻炸。
3. **导出物结构**：CSV 表头与行数、GatingML 的 ISAC 2.0 命名空间与门元素数量。

## 已知干扰项（不要误判成 bug）

- **Windows 下 pytest 会有 16～17 项 ERROR**：根因是 `%TEMP%\pytest-of-18519`
  目录权限被锁（`PermissionError: [WinError 5]`），fixture 建不出来，
  与业务代码无关。项目共 72 个测试，Linux CI 全过；Windows 本地 56 通过、
  16 个卡在临时目录。换可写 TEMP 或 Linux 环境即可复现全绿。
- **Logicle 显示模式下不能画门**：UI 限制，要切回线性坐标再画。
- **`$SPILLOVER` 损坏或检测器名对不上**：页面会红字提示「当前为未补偿数据」，
  比例会偏，这是有意降级而不是静默出错。
- **17 MB 文件首次解析要十几秒**（有缓存，第二次很快）。

## 验证不了的部分（这才是「能不能给别人用」的真问题）

- **没有在线 Demo**：只有 `localhost:3000` + `127.0.0.1:8000`，仓库里
  README 写的是「HuggingFace Spaces 即将上线」。任何陌生人点进 GitHub
  都看不到可用的东西。
- **没和 FlowJo 对拍**：README 自己列为 TODO。上面 16 项证明的是「自洽」，
  不是「跟商用软件一致」。准不准还缺一份对照数据。
- 项目自己警告：无鉴权、无文件清理、上传明文落盘，**不要暴露到公网**。

## 前端首页 500 / 404 的处置（实测踩过）

首页偶发 `500`，日志报 `ENOENT ... .next\server\app\page.js`。原因不是代码，
而是仓库放在 OneDrive 同步目录里，`.next` 构建产物被同步挪走。处置：

```powershell
# 结束占用 3000 的进程，删缓存，重启 dev
$c = Get-NetTCPConnection -LocalPort 3000 -State Listen
Stop-Process -Id $c[0].OwningProcess -Force
Remove-Item "$repo\frontend\.next" -Recurse -Force
Start-Process cmd.exe -ArgumentList "/c","npm run dev" -WorkingDirectory "$repo\frontend"
```

等 30 秒，`GET /` 与 `GET /upload` 都应为 200。长期解法是把仓库移出 OneDrive 目录。

## 怎么起服务

```powershell
$repo = "C:\Users\18519\OneDrive\桌面\github项目\flowgate"
# 后端
Start-Process -FilePath "$repo\backend\.venv\Scripts\python.exe" `
  -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000" `
  -WorkingDirectory "$repo\backend" -WindowStyle Hidden
# 前端
Start-Process -FilePath "cmd.exe" -ArgumentList "/c","npm run dev" `
  -WorkingDirectory "$repo\frontend" -WindowStyle Hidden
```

等约 30 秒再跑验证脚本。
