# FlowGate 单容器镜像：nginx(7860) -> Next(3000) + FastAPI(8000)
# 单入口对外，/api 由 nginx 直接转发后端，绕开 Next 代理的请求体上限。

FROM node:22-bookworm-slim AS fe
WORKDIR /build
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
    && apt-get install -y --no-install-recommends nginx ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

# Next standalone 运行时需要 node 二进制
COPY --from=fe /usr/local/bin/node /usr/local/bin/node
COPY --from=fe /build/.next/standalone /srv/next
COPY --from=fe /build/.next/static /srv/next/frontend/.next/static
COPY --from=be /app /app/be

COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/start.sh /start.sh
RUN chmod +x /start.sh

ENV PORT=3000 \
    HOSTNAME=127.0.0.1 \
    NODE_ENV=production \
    FLOWGATE_UPLOAD_DIR=/app/be/uploads \
    FLOWGATE_GATES_DIR=/app/be/gates \
    FLOWGATE_MAX_UPLOAD_MB=500

EXPOSE 7860
CMD ["/start.sh"]
