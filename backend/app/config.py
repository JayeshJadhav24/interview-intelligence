from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database — set DATABASE_URL in .env
    database_url: str = "postgresql+asyncpg://localhost:5432/interview_dev"

    # Auth
    jwt_secret_key: str = "change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # EPAM Dial API
    dial_api_key: str = ""
    dial_api_base_url: str = "https://ai-proxy.lab.epam.com/openai/v1"
    primary_model: str = "gpt-4.1-mini-2025-04-14"
    eval_model: str = "gpt-4o"

    # Backend
    backend_cors_origins: list[str] = ["http://localhost:3000"]
    environment: str = "development"
    max_upload_size_bytes: int = 5_242_880  # 5 MB


@lru_cache
def get_settings() -> Settings:
    return Settings()
