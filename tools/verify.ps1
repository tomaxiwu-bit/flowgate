param(
    [string]$Repo = (Split-Path -Parent $PSScriptRoot),
    [switch]$StartServices
)

# One-shot verifier for FlowGate.
# Exit 0 = all checks passed.

$ErrorActionPreference = "Continue"

function Test-PortOpen([int]$Port) {
    $r = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -WarningAction SilentlyContinue
    return $r.TcpTestSucceeded
}

$repoRoot = if (Test-Path (Join-Path $Repo "backend")) { $Repo } else {
    "C:\Users\18519\OneDrive\桌面\github项目\flowgate"
}
$python = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
$verifier = Join-Path $repoRoot "tools\verify_e2e.py"

if (-not (Test-Path $python)) {
    Write-Host "venv python not found: $python" -ForegroundColor Red
    exit 2
}

if (-not (Test-PortOpen 8000)) {
    if ($StartServices) {
        Write-Host "backend down, starting uvicorn..." -ForegroundColor Yellow
        $logDir = Join-Path $env:TEMP "flowgate-verify"
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        Start-Process -FilePath $python `
            -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
            -WorkingDirectory (Join-Path $repoRoot "backend") `
            -RedirectStandardOutput (Join-Path $logDir "api.log") `
            -RedirectStandardError (Join-Path $logDir "api.err") `
            -WindowStyle Hidden
        for ($i = 0; $i -lt 20; $i++) {
            Start-Sleep -Seconds 1
            if (Test-PortOpen 8000) { break }
        }
    }
}

if (-not (Test-PortOpen 8000)) {
    Write-Host "backend not reachable on 127.0.0.1:8000. Run with -StartServices or start uvicorn manually." -ForegroundColor Red
    exit 2
}

& $python $verifier
$code = $LASTEXITCODE
Write-Host ""
Write-Host "verify_e2e.py exit code: $code" -ForegroundColor $(if ($code -eq 0) { "Green" } else { "Red" })
exit $code
