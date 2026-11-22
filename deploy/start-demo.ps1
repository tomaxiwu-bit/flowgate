# flowgate 一键公网演示：起后端 + 前端 + Cloudflare 隧道，打印公网地址
# 用法：  powershell -ExecutionPolicy Bypass -File deploy\start-demo.ps1
#         powershell -File deploy\start-demo.ps1 -Port 3001
# 停止：Ctrl+C 后脚本会清理自己起的三个进程

param(
    [int]$Port = 3001,
    [int]$ApiPort = 8000,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root ".demo-logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-Port($p) {
    return [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

# ---------- 1. 后端 ----------
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    throw "找不到后端虚拟环境：$py`n先执行：cd backend && uv sync"
}

if (Test-Port $ApiPort) {
    Write-Host "[1/4] 端口 $ApiPort 已被占用，复用现有后端" -ForegroundColor Yellow
    $api = $null
} else {
    Write-Host "[1/4] 启动后端 :$ApiPort ..." -ForegroundColor Cyan
    $api = Start-Process -FilePath $py -ArgumentList @(
        "-m", "uvicorn", "app.main:app", "--app-dir", (Join-Path $root "backend"),
        "--host", "127.0.0.1", "--port", "$ApiPort"
    ) -RedirectStandardOutput (Join-Path $logDir "api.log") `
       -RedirectStandardError  (Join-Path $logDir "api.err") -WindowStyle Hidden -PassThru
}

# ---------- 2. 前端 ----------
$fe = Join-Path $root "frontend"
$standalone = Join-Path $fe ".next\standalone\frontend\server.js"

if (-not $SkipBuild -and -not (Test-Path $standalone)) {
    Write-Host "[2/4] 首次运行，构建前端（约 1 分钟）..." -ForegroundColor Cyan
    Push-Location $fe
    & cmd.exe /c "npm run build"
    Pop-Location
    if (-not (Test-Path $standalone)) { throw "构建完成但找不到 $standalone" }
}

if (Test-Path (Join-Path $fe ".next\static")) {
    Copy-Item (Join-Path $fe ".next\static") (Join-Path $fe ".next\standalone\frontend\.next\static") -Recurse -Force
}

if (Test-Port $Port) {
    Write-Host "[2/4] 端口 $Port 已被占用，复用现有前端" -ForegroundColor Yellow
    $web = $null
} else {
    Write-Host "[2/4] 启动前端 :$Port ..." -ForegroundColor Cyan
    $env:PORT = "$Port"
    $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:$ApiPort"
    $web = Start-Process -FilePath "node.exe" -ArgumentList "server.js" `
        -WorkingDirectory (Join-Path $fe ".next\standalone\frontend") `
        -RedirectStandardOutput (Join-Path $logDir "web.log") `
        -RedirectStandardError  (Join-Path $logDir "web.err") -WindowStyle Hidden -PassThru
}

Start-Sleep -Seconds 10

# ---------- 3. cloudflared ----------
$cf = Join-Path $env:LOCALAPPDATA "flowgate\cloudflared.exe"
if (-not (Test-Path $cf)) {
    Write-Host "[3/4] 首次运行，下载 cloudflared（约 53MB）..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path (Split-Path $cf) | Out-Null
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 300 `
        -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
        -OutFile $cf
}

Write-Host "[3/4] 建立公网隧道 ..." -ForegroundColor Cyan
$cfLog = Join-Path $logDir "tunnel.log"
$cfErr = Join-Path $logDir "tunnel.err"
$tun = Start-Process -FilePath $cf -ArgumentList @(
    "tunnel", "--url", "http://127.0.0.1:$Port", "--no-autoupdate",
    "--logfile", $cfLog, "--loglevel", "info"
) -RedirectStandardOutput (Join-Path $logDir "tunnel.out") `
   -RedirectStandardError $cfErr -WindowStyle Hidden -PassThru

# ---------- 4. 取地址 ----------
$url = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    $txt = (Get-Content $cfErr -Raw -ErrorAction SilentlyContinue) + (Get-Content $cfLog -Raw -ErrorAction SilentlyContinue)
    $m = [regex]::Match($txt, 'https://[a-z0-9-]+\.trycloudflare\.com')
    if ($m.Success) { $url = $m.Value; break }
    if ($tun.HasExited) { break }
}

if (-not $url) {
    Write-Host "[4/4] 没拿到公网地址，看日志：$cfErr" -ForegroundColor Red
} else {
    # 自检
    $ok = $false
    for ($i = 0; $i -lt 6; $i++) {
        try {
            $r = Invoke-WebRequest "$url/api/health" -TimeoutSec 20 -SkipHttpErrorCheck
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch { }
        Start-Sleep -Seconds 3
    }

    Write-Host ""
    Write-Host "==============================================" -ForegroundColor Green
    Write-Host "  公网地址：$url" -ForegroundColor Green
    Write-Host "  API 文档：$url/docs" -ForegroundColor Green
    Write-Host "  健康检查：$(if ($ok) { '通过' } else { '未通过，见日志' })" -ForegroundColor $(if ($ok) { "Green" } else { "Red" })
    Write-Host "==============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "地址随隧道重建会变；本机不关、进程不退时才可访问。" -ForegroundColor DarkGray
    Write-Host "按 Ctrl+C 停止全部服务。" -ForegroundColor DarkGray
}

# ---------- 保持运行 ----------
try {
    while ($true) {
        Start-Sleep -Seconds 5
        if ($tun.HasExited) { Write-Host "隧道已退出" -ForegroundColor Red; break }
    }
} finally {
    foreach ($p in @($tun, $web, $api)) {
        if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
    Write-Host "已清理进程。" -ForegroundColor DarkGray
}
