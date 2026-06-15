# Dynasty draft engine + Blackbook
# Live rookie drafts: Blackbook /leagues/[id]/rookie-draft
# Legacy Streamlit (just app): local engine debugging only — not deployed

set dotenv-load := true

default:
    @just --list

# Install / update dependencies
install:
    uv sync

# Run the legacy Streamlit UI locally (engine debugging only — not deployed)
app:
    uv run streamlit run dynasty_draft/app.py

# Alias for local Streamlit app
pickbook: app

# Alias for `just app`
run: app

# Use polling file watcher if auto-reload doesn't pick up saves (e.g. some network drives)
app-poll:
    uv run streamlit run dynasty_draft/app.py --server.fileWatcherType poll

# CLI: one-shot draft sync
sync:
    uv run dynasty-draft sync

# CLI: poll Sleeper draft in terminal
watch:
    uv run dynasty-draft watch

# CLI: static strategy notes from war.csv
insights:
    uv run dynasty-draft insights

# --- Blackbook (Phase 0+) ---

# Start local Postgres for Blackbook (port 5444)
bb-db:
    docker compose up -d postgres

# Apply Alembic migrations
bb-migrate:
    uv run alembic upgrade head

# Seed settings + leagues into Postgres
bb-seed:
    uv run python -m backend.seed

# Run Blackbook FastAPI (reloads when Python files change — use bb-api-stable during draft night)
bb-api:
    uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# Same API without auto-reload (stays up while you edit files)
bb-api-stable:
    uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000

# API + Next.js dev servers together
bb-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'kill 0' EXIT
    just bb-api-stable &
    just bb-web

# Sync one league (ingest + metrics + rankings); pass league_id — no API required
bb-sync league_id:
    uv run python -m backend.sync_cli {{league_id}}

# Sync all seeded leagues — no API required
bb-sync-all:
    uv run python -m backend.sync_cli

# Sync all seeded leagues and bypass metric caches
bb-sync-all-force:
    uv run python -m backend.sync_cli --force-refresh

# Run the same job the scheduler uses (starts Postgres, logs to .cache/bb-sync.log)
bb-sync-cron:
    ./scripts/bb-sync-cron.sh

# Install daily launchd job (macOS) — reads SYNC_CRON from env for hour/minute
bb-scheduler-install:
    ./scripts/install-bb-scheduler.sh

# Remove launchd scheduler
bb-scheduler-uninstall:
    ./scripts/uninstall-bb-scheduler.sh

# Re-apply current formula to stored history inputs (§15.1)
bb-recompute-history:
    curl -s -X POST http://127.0.0.1:8000/admin/recompute-history | python3 -m json.tool

# Run Blackbook Next.js frontend
bb-web:
    cd frontend && npm run dev

