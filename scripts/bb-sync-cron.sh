#!/usr/bin/env bash
# Scheduled Blackbook sync — ingest Sleeper → OVR inputs → history (§9.1).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

mkdir -p .cache
LOG_FILE="${BB_SYNC_LOG:-$REPO_ROOT/.cache/bb-sync.log}"

log() {
  echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" >>"$LOG_FILE"
}

log "sync start"

if command -v docker >/dev/null 2>&1; then
  docker compose up -d postgres >>"$LOG_FILE" 2>&1 || log "postgres start failed (continuing)"
fi

if ! uv run python -m backend.sync_cli >>"$LOG_FILE" 2>&1; then
  log "sync failed"
  exit 1
fi

log "sync ok"
