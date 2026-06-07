#!/usr/bin/env bash
# Install daily Blackbook sync via macOS launchd (preferred over cron on Darwin).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_LABEL="com.blackbook.sync"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
SYNC_CRON="${SYNC_CRON:-0 6 * * *}"

# Parse hour/minute from SYNC_CRON (minute hour * * *)
read -r SYNC_MINUTE SYNC_HOUR _ _ _ <<<"$(echo "$SYNC_CRON" | tr ' ' '\n' | head -5 | tr '\n' ' ')"

chmod +x "$REPO_ROOT/scripts/bb-sync-cron.sh"
mkdir -p "$REPO_ROOT/.cache" "$HOME/Library/LaunchAgents"

sed \
  -e "s|__REPO_ROOT__|$REPO_ROOT|g" \
  -e "s|__SYNC_HOUR__|${SYNC_HOUR:-6}|g" \
  -e "s|__SYNC_MINUTE__|${SYNC_MINUTE:-0}|g" \
  "$REPO_ROOT/scripts/com.blackbook.sync.plist.template" >"$PLIST_DEST"

launchctl bootout "gui/$(id -u)/$PLIST_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

echo "Installed $PLIST_LABEL → daily at ${SYNC_HOUR:-6}:$(printf '%02d' "${SYNC_MINUTE:-0}")"
echo "  Plist: $PLIST_DEST"
echo "  Log:   $REPO_ROOT/.cache/bb-sync.log"
echo "  Test:  $REPO_ROOT/scripts/bb-sync-cron.sh"
