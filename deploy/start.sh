#!/bin/sh
set -e

# 单端口对外：Next standalone 监听 $PORT，内部把 /api/* 转发给 127.0.0.1:8000。
# 平台提供的公网域名必须同时进 TrustedHost 与 CORS 白名单，否则写入类请求会被 403。

API_PORT=8000
PORT="${PORT:-8080}"

HOST=""
# 自建部署用通用变量；Render 与 HF 各自注入自己的域名变量
if [ -n "$FLOWGATE_PUBLIC_HOST" ]; then HOST="$FLOWGATE_PUBLIC_HOST"; fi
if [ -z "$HOST" ] && [ -n "$RENDER_EXTERNAL_HOSTNAME" ]; then HOST="$RENDER_EXTERNAL_HOSTNAME"; fi
if [ -z "$HOST" ] && [ -n "$SPACE_HOST" ]; then HOST="$SPACE_HOST"; fi

if [ -n "$HOST" ]; then
  export FLOWGATE_TRUSTED_HOSTS="localhost,127.0.0.1,backend,${HOST}"
  export FLOWGATE_CORS_ORIGINS="https://${HOST},http://localhost:3000"
fi

# 前端 rewrite 的后端地址；api.ts 在生产用同源相对路径，不依赖这个变量注入到浏览器
export NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:${API_PORT}"
export HOSTNAME="0.0.0.0"
export PORT

echo "[start] port=${PORT} host=${HOST:-none}"
echo "[start] trusted_hosts=${FLOWGATE_TRUSTED_HOSTS:-default}"
echo "[start] cors=${FLOWGATE_CORS_ORIGINS:-default}"

# 依赖装在系统环境里（见 Dockerfile 的 be 阶段说明），直接用镜像自带 python3。
# 若外部自行挂载了 venv，也仍然可用。
PY=python3
if [ -x /app/be/.venv/bin/python3 ]; then PY=/app/be/.venv/bin/python3; fi
echo "[start] python=${PY}"

"$PY" -m uvicorn app.main:app \
    --app-dir /app/be --host 127.0.0.1 --port "$API_PORT" &
API_PID=$!

node /srv/next/frontend/server.js &
WEB_PID=$!

echo "[start] api_pid=${API_PID} web_pid=${WEB_PID}"

# 任一进程退出即让容器退出，交给平台重启，而不是留一个半死状态
while true; do
  sleep 20
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "[start] 后端进程已退出"
    exit 1
  fi
  if ! kill -0 "$WEB_PID" 2>/dev/null; then
    echo "[start] 前端进程已退出"
    exit 1
  fi
done
