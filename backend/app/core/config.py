from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "CheckWise API"
    API_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    CHECKWISE_ENV: str = "local"

    DATABASE_URL: str = "postgresql+psycopg://checkwise:checkwise@localhost:5432/checkwise"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    STORAGE_BACKEND: str = "local"
    STORAGE_BUCKET: str = "checkwise-local"
    STORAGE_PUBLIC_BASE_URL: str = ""
    LOCAL_STORAGE_PATH: str = "./storage"

    MAX_UPLOAD_SIZE_BYTES: int = 15 * 1024 * 1024
    ALLOWED_FILE_EXTENSIONS: str = ".pdf"
    SUPPORT_WHATSAPP_URL: str = ""
    SUPPORT_QR_PLACEHOLDER_URL: str = ""

    # Auth + RBAC (Patch 6). The default secret is for local dev only;
    # any non-local environment must override AUTH_JWT_SECRET via env.
    AUTH_JWT_SECRET: str = "checkwise-local-dev-secret-change-me-please-min-32-chars"
    AUTH_JWT_ALGORITHM: str = "HS256"
    AUTH_JWT_EXPIRES_MINUTES: int = 60 * 24
    AUTH_BCRYPT_ROUNDS: int = 12

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_extensions_set(self) -> set[str]:
        return {
            ext.strip().lower() for ext in self.ALLOWED_FILE_EXTENSIONS.split(",") if ext.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
