#!/usr/bin/env bash
set -euo pipefail

PLIST_LABEL="com.blackbook.sync"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

launchctl bootout "gui/$(id -u)/$PLIST_LABEL" 2>/dev/null || true
rm -f "$PLIST_DEST"

echo "Removed $PLIST_LABEL"
