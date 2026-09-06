FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# 先装依赖（利用层缓存）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# 再拷源码
COPY app ./app
COPY scripts ./scripts

ENV PATH="/app/.venv/bin:$PATH"
ENV FLOWGATE_UPLOAD_DIR=/data/uploads
ENV FLOWGATE_GATES_DIR=/data/gates

EXPOSE 8000
VOLUME ["/data"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
