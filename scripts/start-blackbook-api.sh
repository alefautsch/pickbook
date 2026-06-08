#!/usr/bin/env sh
set -e

if [ "${RUN_DB_MIGRATIONS:-true}" = "true" ]; then
  uv run alembic upgrade head
fi

if [ "${SEED_DB:-true}" = "true" ]; then
  uv run python -m backend.seed
fi

PORT="${PORT:-8000}"
exec uv run uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
