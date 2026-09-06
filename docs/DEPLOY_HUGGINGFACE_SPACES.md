# 部署在线 Demo（HuggingFace Spaces 免费方案）

> 目标：让招聘方/导师**不安装任何东西**就能在浏览器打开你的 Demo。
> 方式：HuggingFace Spaces 免费 Docker Space（公开项目零成本，需 GitHub 账号授权登录 HF）。

## 为什么是 HuggingFace Spaces

| 平台 | 免费额度 | Docker 支持 | 备注 |
|---|---|---|---|
| HuggingFace Spaces | 公开 Space 免费（CPU 基础档） | 是 | 生物信息社区认可度高，简历链接加分 |
| Vercel | Hobby 免费 | 是（单容器） | 无持久卷，后端上传目录会丢 |
| Render | 免费档休眠 | 是 | 冷启动慢 |
| 自建 VPS | 花钱 | 是 | 不建议学生期投入 |

## 方案 A：单容器（推荐，Spaces 默认形态）

HF Spaces 只认**根目录一个 Dockerfile**。FlowGate 前后端合成一个容器：

```dockerfile
# ===== 阶段 1：构建前端 =====
FROM node:22-alpine AS fe
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ ./
ARG NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN npm run build

# ===== 阶段 2：后端运行时（uv 静态 Python）=====
FROM python:3.12-slim AS be
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/app ./app
RUN mkdir -p uploads gates

# ===== 阶段 3：合并，用单一入口进程 =====
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=be /app /app
COPY --from=fe /fe/.next /app/static_next
COPY deploy/start.sh /start.sh
RUN chmod +x /start.sh
ENV FLOWGATE_UPLOAD_DIR=/app/uploads \
    FLOWGATE_GATES_DIR=/app/gates \
    FLOWGATE_CORS_ORIGINS=https://YOUR_USERNAME-flowgate.hf.space
EXPOSE 7860
CMD ["/start.sh"]
```

`deploy/start.sh`（后端 :8000 + 前端独立端口，前端把 /api 代理到后端）：

```bash
#!/bin/sh
set -e
# 后端
FLOWGATE_CORS_ORIGINS="$FLOWGATE_CORS_ORIGINS" \
  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACK_PID=$!
# 前端（standalone 产物）
PORT=7860 HOSTNAME=0.0.0.0 \
  node /app/static_next/server.js &
FRONT_PID=$!
trap "kill $BACK_PID $FRONT_PID" EXIT
wait
```

> 说明：HF Spaces 默认对外端口 7860。前端用 Next standalone 产物启动，
> `NEXT_PUBLIC_API_BASE_URL` 需要在**前端构建时**指向后端地址（单容器内
> 即 `http://127.0.0.1:8000`）；浏览器里前端自己的页面从同源 7860 提供，
> `/api/*` 通过前端 rewrite 转发到后端 8000。

## 方案 B：双容器（本地 docker compose 已有，自托管时用）

```bash
cd flowgate
docker compose up -d --build
# 或带远程域名
FLOWGATE_API_BASE_URL=https://api.your-domain.com \
FLOWGATE_CORS_ORIGINS=https://app.your-domain.com \
docker compose up -d --build
```

## 上线步骤（10 分钟）

1. 推 GitHub：`git remote add origin https://github.com/<你>/flowgate.git && git push -u origin main`
2. 用 GitHub 账号登录 https://huggingface.co，新建 Space：
   - Name: `flowgate`
   - License: MIT
   - SDK: **Docker**
   - Hardware: CPU basic（免费）
3. 把上面「方案 A」的 Dockerfile 与 `deploy/start.sh` 放到仓库根并推送，Spaces 自动构建
4. 首次构建约 5-10 分钟，构建完成后访问 `https://<你>-flowgate.hf.space`
5. 在 README 顶部加 Demo 徽章：

```markdown
[![Try FlowGate](https://img.shields.io/badge/Demo-Try%20FlowGate-9EACEA)](https://YOUR_USERNAME-flowgate.hf.space)
```

## 注意事项

- Space 重启后 `uploads/`、`gates/` 会被重置（无持久卷）——Demo 定位是"可体验"，不是生产存储；README 与页面都注明这一点。
- 上传大小限制保留 500MB 上限（文件写入容器内存盘，过大会拖垮免费档）。
- CORS 环境变量必须与 Space 域名一致，否则前端跨域被拦。
- 若用免费 CPU 档，29 万事件的 8 色样本绘制约 1-3 秒，属正常。
