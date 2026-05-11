"""Application settings (env-driven)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "local"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./dev.db"

    jwt_secret: str = "dev-secret-change-me-please-32-chars"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 480

    demo_user_email: str = "demo@spaceship.test"
    demo_user_password: str = "demo123"
    demo_user_client_id: str = ""

    llm_provider: str = "keyword"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""

    fallback_provider: str = "keyword"
    fallback_model: str = ""
    fallback_api_key: str = ""
    fallback_base_url: str = ""

    fallback2_provider: str = "keyword"
    fallback2_model: str = ""
    fallback2_api_key: str = ""
    fallback2_base_url: str = ""

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
