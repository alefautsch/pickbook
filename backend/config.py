from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend environment settings (§9, Phase 0).

    Values come from the environment or a local `.env` file. `DATABASE_URL`
    is the only hard requirement; the rest have sensible defaults for local dev.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://blackbook:blackbook@localhost:5444/blackbook"
    sleeper_username: str = "alefautsch"
    anthropic_api_key: str | None = None

    # Comma-separated list of allowed CORS origins for the frontend.
    cors_origins: str = "http://localhost:3000"

    # Documented cron cadence for sync (external runner — §9.1). Not used in-process.
    sync_cron: str = "0 6 * * *"
    sync_enabled: bool = True

    # Optional gate for POST /admin/recompute-history (personal tool).
    admin_token: str | None = None

    # Top-N unrostered players scored per league at sync for the FA board (§14.2).
    fa_pool_size: int = 150

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
