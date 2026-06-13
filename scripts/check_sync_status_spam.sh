#!/usr/bin/env bash
# Load a page and fail if sync/status hits the backend too often after load.
set -euo pipefail

URL="${1:-http://localhost:3000/leagues/1314731206859853824}"
WINDOW_SEC="${2:-3}"
MAX_BROWSER_REQUESTS="${3:-2}"
WAIT_SEC="${4:-8}"
LOG="/tmp/bb-sync-status-hits.log"

rm -f "$LOG"
START_MS=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)

echo "Loading $URL ..."
agent-browser close --all 2>/dev/null || true
agent-browser set viewport 390 844 >/dev/null
agent-browser open "$URL" >/dev/null
sleep "$WAIT_SEC"

python3 - "$LOG" "$START_MS" "$WINDOW_SEC" "$MAX_BROWSER_REQUESTS" <<'PY'
import sys
import time
from collections import Counter
from pathlib import Path

log_path = Path(sys.argv[1])
start_ms = int(sys.argv[2])
window_sec = float(sys.argv[3])
max_browser = int(sys.argv[4])
now_ms = int(time.time() * 1000)
window_ms = int(window_sec * 1000)

rows = []
if log_path.exists():
    for line in log_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            ts = int(float(parts[0]))
            caller = parts[1]
        except ValueError:
            continue
        if ts < start_ms:
            continue
        if now_ms - ts > window_ms:
            continue
        rows.append(caller)

counts = Counter(rows)
browser = counts.get("browser", 0)
unknown = counts.get("unknown", 0)
print(f"Logged hits in last {window_sec:.0f}s: {dict(counts)}")
print(f"  browser-tagged (new code): {browser}")
print(f"  unknown (likely stale tabs): {unknown}")

if browser > max_browser:
    print(f"FAIL: browser-tagged sync/status exceeded {max_browser} in {window_sec:.0f}s")
    raise SystemExit(1)

if unknown > 0:
    print("NOTE: stale browser tabs may still spam until hard-refreshed; proxy now caches for 5s.")

print("ok")
PY
