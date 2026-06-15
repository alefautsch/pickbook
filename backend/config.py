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
    # Cheaper model for structured trade-validation JSON (Haiku default).
    llm_validation_model: str = "claude-haiku-4-5"
    # Route free-form advisor questions via Haiku intent classifier + tool DAG (vs tool loop).
    llm_advisor_router_enabled: bool = True
    # Moonshot API — Kimi models in the in-season advisor. Optional.
    moonshot_api_key: str | None = None
    # Brave Search API — advisor web_search tool (injury/news). Optional.
    brave_api_key: str | None = None

    # Comma-separated list of allowed CORS origins for the frontend.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # In-process sync scheduler cadence. Cron expressions are evaluated in UTC.
    sync_cron: str = "0 6 * * *"
    sync_enabled: bool = True

    # Optional gate for POST /admin/recompute-history (personal tool).
    admin_token: str | None = None

    # Top-N unrostered players scored per league at sync for the FA board (§14.2).
    fa_pool_size: int = 150

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def sqlalchemy_database_url(url: str) -> str:
    """Use the installed psycopg driver for Railway's plain postgresql URLs."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
