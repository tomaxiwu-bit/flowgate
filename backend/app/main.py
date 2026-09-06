"""FlowGate FastAPI 应用入口。

启动方式（backend 目录下）:
    uv run uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import events, export, files, gates, health
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="FlowGate API",
    description="免费开源的流式细胞术 Web 分析工具 - 后端 API",
    version="0.1.0",
)

# 开发阶段允许本地前端跨域；上线前收紧为具体域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(gates.router, prefix="/api")
app.include_router(export.router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    """根路径：返回服务信息。"""
    return {"service": "FlowGate API", "docs": "/docs", "health": "/api/health"}
