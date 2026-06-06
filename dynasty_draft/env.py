from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"


def load_env() -> None:
    """Load environment variables from the project-root `.env` if present."""
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)
