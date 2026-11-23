# FlowGate 单容器镜像：Next standalone 监听 $PORT，/api 由 Next 转发到 FastAPI(8000)
#
# 目录布局必须与 outputFileTracingRoot（next.config.ts 里的 ".."）对齐：
#   本地： <repo>/frontend  -> tracing root = <repo> -> .next/standalone/frontend/server.js
#   镜像： /src/frontend   -> tracing root = /src    -> .next/standalone/frontend/server.js
# 若把 frontend 直接放在 /build，tracing root 会变成 /，standalone 产物结构跟着变，
# server.js 就不在 /srv/next/frontend/ 下，启动会找不到入口。

FROM node:22-bookworm-slim AS fe
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM python:3.12-slim AS be
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/app ./app
RUN mkdir -p uploads gates

FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# Next standalone 运行时需要 node 二进制
COPY --from=fe /usr/local/bin/node /usr/local/bin/node
COPY --from=fe /src/frontend/.next/standalone /srv/next
COPY --from=fe /src/frontend/.next/static /srv/next/frontend/.next/static
COPY --from=be /app /app/be

COPY deploy/start.sh /start.sh
RUN chmod +x /start.sh

# 512MB 免费实例的保守默认值：限制单文件大小、缩短 Sample 缓存，
# 避免多个大文件同时驻留把内存打满。需要更大规模时用环境变量覆盖。
ENV NODE_ENV=production \
    FLOWGATE_UPLOAD_DIR=/app/be/uploads \
    FLOWGATE_GATES_DIR=/app/be/gates \
    FLOWGATE_MAX_UPLOAD_MB=100 \
    FLOWGATE_SAMPLE_CACHE_SIZE=2

EXPOSE 8080
CMD ["/start.sh"]
