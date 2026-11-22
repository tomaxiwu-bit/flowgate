#!/bin/sh
set -e

# HuggingFace Space 会注入 SPACE_HOST（例如 xxx-flowgate.hf.space）。
# 后端默认只信任 localhost，公网域名必须显式放行，否则所有请求都会被 TrustedHost 拒掉。
HOST="${SPACE_HOST:-tomaxiwww-flowgate.hf.space}"
export FLOWGATE_TRUSTED_HOSTS="localhost,127.0.0.1,backend,${HOST}"
export FLOWGATE_CORS_ORIGINS="https://${HOST},http://localhost:3000"

echo "[start] trusted_hosts=${FLOWGATE_TRUSTED_HOSTS}"
echo "[start] cors=${FLOWGATE_CORS_ORIGINS}"

/app/be/.venv/bin/python -m uvicorn app.main:app \
    --app-dir /app/be --host 127.0.0.1 --port 8000 &
API_PID=$!

node /srv/next/frontend/server.js &
WEB_PID=$!

# 给后端一点热身时间（FlowKit 首次导入较慢），nginx 就绪后即可对外
sleep 10

echo "[start] api_pid=${API_PID} web_pid=${WEB_PID}, handing over to nginx on 7860"
exec nginx -g "daemon off;"
