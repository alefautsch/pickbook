"""LeagueScoringContext — per-league lens for OVR (§6)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from dynasty_draft.draft_context import build_scoring_context
from dynasty_draft.projections import _replacement_index
from dynasty_draft.recommender import DraftState
from dynasty_draft.war_data import POSITIONS

from backend.db.models import League


def _superflex_from_roster(roster_positions: list[str]) -> bool:
    return any(pos.upper() in {"SUPER_FLEX", "SUPERFLEX", "QB_WR_RB_TE"} for pos in roster_positions)


@dataclass(frozen=True)
class LeagueScoringContext:
    """Scoring lens derived from a leagues row (§6)."""

    league_id: str
    name: str
    season: str
    team_count: int
    superflex: bool
    ppr: float
    te_premium: float
    pass_td_points: float
    pass_td_40_bonus: float | None
    rec_td_40_bonus: float | None
    rush_td_40_bonus: float | None
    roster_positions: list[str]
    replacement_rank: dict[str, int]
    summary: str
    source: str
    context_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "league_id": self.league_id,
            "name": self.name,
            "season": self.season,
            "team_count": self.team_count,
            "superflex": self.superflex,
            "ppr": self.ppr,
            "te_premium": self.te_premium,
            "pass_td_points": self.pass_td_points,
            "pass_td_40_bonus": self.pass_td_40_bonus,
            "rec_td_40_bonus": self.rec_td_40_bonus,
            "rush_td_40_bonus": self.rush_td_40_bonus,
            "roster_positions": self.roster_positions,
            "replacement_rank": self.replacement_rank,
            "summary": self.summary,
            "source": self.source,
            "context_hash": self.context_hash,
        }


def _compute_context_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _minimal_draft_state(league_row: League) -> DraftState:
    """Minimal DraftState shell so build_scoring_context semantics match Pickbook."""
    from dynasty_draft.war_loader import load_war_data

    settings = {"dynasty_daddy": {"enabled": True}, "war_csv": "war.csv"}
    try:
        war, _meta = load_war_data(settings, league_row=league_row)
    except (FileNotFoundError, ValueError):
        from dynasty_draft.war_data import WarData

        war = WarData.empty()
    league_dict = {
        "league_id": league_row.sleeper_league_id,
        "name": league_row.name,
        "season": league_row.season,
        "total_rosters": league_row.total_rosters,
        "roster_positions": league_row.roster_positions_json,
        "scoring_settings": league_row.scoring_json,
    }
    fake_draft = {
        "settings": {"teams": league_row.total_rosters, "rounds": 1},
        "type": "snake",
        "draft_order": {},
        "slot_to_roster_id": {},
    }
    return DraftState(
        draft=fake_draft,
        picks=[],
        league=league_dict,
        user_id="",
        war=war,
        sleeper_players={},
    )


def build_league_scoring_context(league_row: League) -> LeagueScoringContext:
    """Build LeagueScoringContext from a leagues DB row."""
    roster_positions = list(league_row.roster_positions_json or [])
    superflex = league_row.superflex or _superflex_from_roster(roster_positions)
    teams = int(league_row.total_rosters)

    shell = _minimal_draft_state(league_row)
    scoring = build_scoring_context(shell)

    replacement_rank = {
        pos: _replacement_index(
            pos,
            teams=teams,
            roster_positions=roster_positions,
            superflex=superflex,
        )
        for pos in POSITIONS
    }

    identity = {
        "league_id": league_row.sleeper_league_id,
        "scoring": league_row.scoring_json,
        "roster_positions": roster_positions,
        "total_rosters": teams,
        "superflex": superflex,
    }
    context_hash = _compute_context_hash(identity)

    return LeagueScoringContext(
        league_id=league_row.sleeper_league_id,
        name=league_row.name,
        season=league_row.season,
        team_count=teams,
        superflex=superflex,
        ppr=float(scoring.get("ppr", 0.5)),
        te_premium=float(scoring.get("te_premium") or 0),
        pass_td_points=float(scoring.get("pass_td_points", 4)),
        pass_td_40_bonus=scoring.get("pass_td_40_bonus"),
        rec_td_40_bonus=scoring.get("rec_td_40_bonus"),
        rush_td_40_bonus=scoring.get("rush_td_40_bonus"),
        roster_positions=roster_positions,
        replacement_rank=replacement_rank,
        summary=str(scoring.get("summary", "")),
        source=str(scoring.get("source", "sleeper")),
        context_hash=context_hash,
    )
