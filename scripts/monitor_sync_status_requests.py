#!/usr/bin/env python3
"""Watch sync/status request rate via the Next.js proxy hit log.

Usage:
  python scripts/monitor_sync_status_requests.py
  python scripts/monitor_sync_status_requests.py --window 3 --warn 2

Log source (written by frontend proxy in dev):
  /tmp/bb-sync-status-hits.log
Each line: <unix_ms> <caller> <source>
"""

from __future__ import annotations

import argparse
import time
from collections import Counter, deque
from pathlib import Path

LOG_PATH = Path("/tmp/bb-sync-status-hits.log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor sync/status request spam")
    parser.add_argument("--window", type=float, default=3.0, help="Sliding window seconds")
    parser.add_argument("--warn", type=int, default=2, help="Warn if more than N upstream hits in window")
    parser.add_argument("--log", type=Path, default=LOG_PATH, help="Hit log path")
    parser.add_argument("--interval", type=float, default=1.0, help="Print interval seconds")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    hits: deque[tuple[float, str]] = deque()
    offset = 0
    upstream_hits = 0

    if args.log.exists():
        offset = args.log.stat().st_size

    print(f"Monitoring {args.log} (>{args.warn} upstream req / {args.window}s = SPAM)")
    print("-" * 60)

    while True:
        if args.log.exists():
            with args.log.open("r", encoding="utf-8") as fh:
                fh.seek(offset)
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    try:
                        ts_ms = float(parts[0])
                        caller = parts[1] if len(parts) > 1 else "unknown"
                    except ValueError:
                        continue
                    hits.append((ts_ms / 1000.0, caller))
                    if caller != "cached":
                        upstream_hits += 1
                offset = fh.tell()

        now = time.time()
        while hits and hits[0][0] < now - args.window:
            hits.popleft()

        callers = Counter(caller for _, caller in hits)
        count = len(hits)
        label = "SPAM" if count > args.warn else "ok"
        breakdown = ", ".join(f"{k}:{v}" for k, v in callers.most_common()) or "none"
        print(
            f"{time.strftime('%H:%M:%S')}  last {args.window:.0f}s: {count:3d} logged [{label}]  ({breakdown})",
            flush=True,
        )
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
