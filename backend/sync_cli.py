"""CLI entrypoint for scheduled / headless Blackbook sync (§9.1).

Does not require the FastAPI server — suitable for cron and launchd.
"""

from __future__ import annotations

import json
import sys

from backend.db.session import SessionLocal
from backend.services.sync_runner import run_full_league_sync, run_sync_all


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    db = SessionLocal()
    try:
        if len(args) == 1:
            result = run_full_league_sync(db, args[0])
            print(json.dumps(result.model_dump(), indent=2, default=str))
            return 0 if result.status == "success" else 1

        response = run_sync_all(db)
        print(json.dumps(response.model_dump(), indent=2, default=str))
        failed = [r for r in response.results if r.status != "success"]
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
