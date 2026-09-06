"""应用配置模块。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（backend/ 根，config.py 位于 backend/app/core/ 下）
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """应用配置，可通过环境变量或 .env 覆盖。"""

    model_config = SettingsConfigDict(env_prefix="FLOWGATE_", env_file=".env", extra="ignore")

    # 跨域来源（逗号分隔；部署时用 FLOWGATE_CORS_ORIGINS 覆盖，
    # 例如 "https://demo.example.com,http://localhost:3000"）
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # 上传的 FCS 文件临时存储目录
    upload_dir: Path = BACKEND_DIR / "uploads"

    # 门控树 JSON 持久化目录
    gates_dir: Path = BACKEND_DIR / "gates"

    # 单文件大小上限（MB）
    max_upload_mb: int = 500

    @property
    def cors_origin_list(self) -> list[str]:
        """把逗号分隔的 CORS 配置解析为列表。"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """获取全局单例配置。"""
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.gates_dir.mkdir(parents=True, exist_ok=True)
    return settings
