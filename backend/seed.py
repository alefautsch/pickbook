"""Seed Blackbook DB: settings from config.json + leagues from leagues.seed.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

from backend.api.settings import seed_settings_from_config
from backend.db.models import League
from backend.db.session import SessionLocal
from dynasty_draft.sleeper_client import SleeperClient

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "leagues.seed.json"


def _superflex_from_roster(roster_positions: list[str]) -> bool:
    return any(pos.upper() in {"SUPER_FLEX", "SUPERFLEX", "QB_WR_RB_TE"} for pos in roster_positions)


def seed_leagues(db) -> int:
    if not SEED_PATH.exists():
        raise FileNotFoundError(f"Missing seed file: {SEED_PATH}")

    entries = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    client = SleeperClient()
    count = 0

    for entry in entries:
        league_id = str(entry["sleeper_league_id"])
        remote = client.get_league(league_id)
        roster_positions = remote.get("roster_positions") or []
        scoring = remote.get("scoring_settings") or {}
        total_rosters = int(remote.get("total_rosters") or entry.get("total_rosters") or 0)

        row = db.get(League, league_id)
        if row is None:
            row = League(sleeper_league_id=league_id)
            db.add(row)

        row.name = str(remote.get("name") or entry.get("name") or league_id)
        row.season = str(remote.get("season") or entry.get("season") or "2026")
        row.total_rosters = total_rosters
        row.superflex = _superflex_from_roster(roster_positions)
        row.scoring_json = scoring
        row.roster_positions_json = roster_positions
        count += 1

    db.commit()
    return count


def main() -> None:
    db = SessionLocal()
    try:
        settings_count = seed_settings_from_config(db)
        leagues_count = seed_leagues(db)
        league_names = [
            row.name
            for row in db.scalars(select(League).order_by(League.name)).all()
        ]
        print(f"Seeded {settings_count} settings keys and {leagues_count} leagues.")
        for name in league_names:
            print(f"  - {name}")
    except Exception as exc:
        db.rollback()
        print(f"Seed failed: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
