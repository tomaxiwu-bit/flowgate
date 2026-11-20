"""FlowGate FastAPI 应用入口。

启动方式（backend 目录下）:
    uv run uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from app.api import events, export, files, gates, health
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="FlowGate API",
    description="免费开源的流式细胞术 Web 分析工具 - 后端 API",
    version="0.1.0",
)

# CORS 来源由 FLOWGATE_CORS_ORIGINS 环境变量配置（逗号分隔）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[host.strip() for host in settings.trusted_hosts.split(",") if host.strip()],
    www_redirect=False,
)


@app.middleware("http")
async def guard_browser_writes(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
        if origin not in settings.cors_origin_list and "*" not in settings.cors_origin_list:
            return JSONResponse({"detail": "不允许的请求来源"}, status_code=403)
    return await call_next(request)

app.include_router(health.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(gates.router, prefix="/api")
app.include_router(export.router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    """根路径：返回服务信息。"""
    return {"service": "FlowGate API", "docs": "/docs", "health": "/api/health"}
