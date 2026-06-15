"""Project 2026 rookie-class picks for trade / AI reasoning."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.api.settings import _read_settings
from backend.db.models import League
from backend.services.rookie_draft_service import (
    load_rookie_draft_state_for_league,
    project_remaining_picks,
)
from dynasty_draft.draft_pick_ownership import pick_slot_for_pick_no
from dynasty_draft.war_data import PlayerValue, WarData

ROOKIE_TRADE_SEASON = "2026"
_PICK_LABEL_RE = re.compile(r"(?:\d{4}\s+)?(\d+)\.(\d+)")


def parse_pick_slot_from_label(label: str | None) -> tuple[int, int] | None:
    """Parse '2026 1.04' → (round, slot_in_round)."""
    if not label:
        return None
    match = _PICK_LABEL_RE.search(label.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def pick_no_for_slot(
    *,
    round_no: int,
    slot_in_round: int,
    teams: int,
    rounds: int,
    draft_type: str,
) -> int | None:
    if teams <= 0 or round_no <= 0 or slot_in_round <= 0:
        return None
    draft_type = (draft_type or "snake").lower()
    for pick_no in range(1, teams * rounds + 1):
        if (pick_no - 1) // teams + 1 != round_no:
            continue
        if pick_slot_for_pick_no(pick_no, teams, draft_type) == slot_in_round:
            return pick_no
    return None


def _pick_slot_fields(pick: dict[str, Any]) -> tuple[str, int, int] | None:
    season = str(pick.get("season") or "")
    if season != ROOKIE_TRADE_SEASON:
        return None
    round_no = int(pick.get("round") or 0)
    slot = pick.get("slot_in_round")
    if slot is not None:
        return season, round_no, int(slot)
    parsed = parse_pick_slot_from_label(str(pick.get("label") or ""))
    if parsed is None:
        return None
    round_no = round_no or parsed[0]
    return season, round_no, parsed[1]


def _need_positions(team: dict[str, Any]) -> set[str]:
    positions: set[str] = set()
    for row in team.get("needs") or []:
        if isinstance(row, dict):
            pos = row.get("position") or row.get("pos")
            if pos:
                positions.add(str(pos).upper())
    starter_needs = team.get("starter_needs") or {}
    if isinstance(starter_needs, dict):
        for pos, count in starter_needs.items():
            if pos.upper() in {"QB", "RB", "WR", "TE", "FLEX"} and int(count or 0) > 0:
                positions.add(pos.upper())
    return positions


def _compact_rookie(row: dict[str, Any], *, adp_pick: int | None = None) -> dict[str, Any]:
    return {
        "name": row.get("name"),
        "pos": row.get("pos") or row.get("position"),
        "ovr": row.get("dynasty_rating") or row.get("ovr"),
        "adp_pick": adp_pick if adp_pick is not None else row.get("adp_pick"),
        "trade_value": row.get("trade_value"),
    }


class _NoAdp:
    def pick_no(self, name: str) -> int | None:
        return None


def _rookie_row(player: PlayerValue, rank: int) -> dict[str, Any]:
    return {
        "name": player.name,
        "pos": player.pos,
        "ovr": None,
        "adp_pick": rank,
        "bpa_rank": rank,
        "trade_value": player.trade_value,
        "source": "rookie_board_rank",
    }


def _fallback_rookie_board(db: Session) -> list[dict[str, Any]]:
    """Rookie-only board from WAR when Sleeper has no rookie draft object."""
    settings = _read_settings(db)
    war_path = Path(str(settings.get("war_csv") or "war.csv"))
    if not war_path.exists():
        return []
    war = WarData(war_path)
    rookies = [
        player
        for player in war.players
        if player.pos in {"QB", "RB", "WR", "TE"} and not player.has_worp
    ]
    rookies.sort(key=lambda player: player.trade_value, reverse=True)
    return [_rookie_row(player, rank) for rank, player in enumerate(rookies, start=1)]


def _board_rows_from_state(state: Any, *, limit: int = 500) -> list[dict[str, Any]]:
    adp = state._adp_index()
    rows: list[dict[str, Any]] = []
    for rank, row in enumerate(state.bpa_recommendations(limit=limit), start=1):
        name = row.get("name") or ""
        rows.append(
            {
                "name": name,
                "pos": row.get("pos"),
                "ovr": row.get("dynasty_rating"),
                "adp_pick": row.get("adp_pick") or adp.pick_no(name),
                "bpa_rank": row.get("bpa_rank") or rank,
                "trade_value": row.get("trade_value"),
                "source": "rookie_draft_board",
            }
        )
    return rows


def _projection_from_board_rank(board: list[dict[str, Any]], pick_no: int) -> dict[str, Any] | None:
    if pick_no <= 0 or not board:
        return None
    idx = min(pick_no - 1, len(board) - 1)
    row = dict(board[idx])
    start = max(0, idx - 2)
    end = min(len(board), idx + 3)
    row["nearby_rookies"] = [
        _compact_rookie(candidate, adp_pick=candidate.get("adp_pick"))
        for candidate in board[start:end]
    ]
    return row


def _board_top(state: Any, *, limit: int = 15) -> list[dict[str, Any]]:
    return _board_rows_from_state(state, limit=limit)


def _describe_pick_projection(
    pick: dict[str, Any],
    *,
    pick_no: int,
    projection: dict[str, Any] | None,
    acquired_by: str,
    given_by: str,
    need_positions: set[str],
    adp_index: Any,
) -> dict[str, Any]:
    label = pick.get("label") or f"{ROOKIE_TRADE_SEASON} pick #{pick_no}"
    row: dict[str, Any] = {
        "label": label,
        "pick_no": pick_no,
        "acquired_by": acquired_by,
        "given_by": given_by,
    }
    if projection is None:
        row["projected_rookie"] = None
        row["note"] = "No projection — slot unknown or draft complete"
        return row

    name = str(projection.get("name") or "")
    pos = str(projection.get("pos") or "").upper()
    adp_pick = adp_index.pick_no(name) if name else None
    rookie = _compact_rookie(projection, adp_pick=adp_pick)
    row["projected_rookie"] = rookie
    if projection.get("nearby_rookies"):
        row["nearby_rookies"] = projection["nearby_rookies"]
    row["fills_need_for_acquirer"] = bool(pos and pos in need_positions)
    if pos == "TE":
        row["tep_note"] = "TE premium leagues boost mid-round TE prospects (e.g. Sadiq) vs flat"
    return row


def build_trade_rookie_context(
    db: Session,
    league_id: str,
    *,
    review_team: dict[str, Any],
    other_team: dict[str, Any],
    review_acquires_picks: list[dict[str, Any]],
    review_gives_picks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Simulate who lands at each 2026 pick slot in the trade (review team's POV)."""
    loaded = load_rookie_draft_state_for_league(db, league_id)
    state: Any | None = None
    if loaded is None:
        league_row = db.get(League, league_id)
        if league_row is None or str(league_row.season) != ROOKIE_TRADE_SEASON:
            return None
        board = _fallback_rookie_board(db)
        if not board:
            return None
        projections: dict[int, dict[str, Any]] = {}
        state = None
        teams = int(league_row.total_rosters or 12)
        rounds = max(
            4,
            *[
                fields[1]
                for fields in (
                    _pick_slot_fields(pick)
                    for pick in [*review_acquires_picks, *review_gives_picks]
                )
                if fields is not None
            ],
        )
        draft_type = "linear"
        adp_index: Any = _NoAdp()
        draft_status = None
        picks_made = 0
    else:
        state, league_row = loaded
        draft_season = str(state.draft.get("season") or league_row.season)
        if draft_season != ROOKIE_TRADE_SEASON:
            return None

        projections = project_remaining_picks(state)
        board = _board_rows_from_state(state)
        if not projections and not board:
            return None

        teams = state._teams()
        rounds = state._rounds()
        draft_type = str(state.draft.get("type") or "snake")
        adp_index = state._adp_index()
        draft_status = state.draft.get("status")
        picks_made = len(state.picks)

    if teams <= 0:
        return None

    review_name = str(review_team.get("team_name") or "review team")
    other_name = str(other_team.get("team_name") or "other team")
    review_needs = _need_positions(review_team)
    other_needs = _need_positions(other_team)

    picks_in_trade: list[dict[str, Any]] = []

    def _append_pick(
        pick: dict[str, Any],
        *,
        acquired_by: str,
        given_by: str,
        need_positions: set[str],
    ) -> None:
        fields = _pick_slot_fields(pick)
        if fields is None:
            return
        _, round_no, slot = fields
        pick_no = pick_no_for_slot(
            round_no=round_no,
            slot_in_round=slot,
            teams=teams,
            rounds=rounds,
            draft_type=draft_type,
        )
        if pick_no is None:
            return
        projection = projections.get(pick_no) or _projection_from_board_rank(board, pick_no)
        picks_in_trade.append(
            _describe_pick_projection(
                pick,
                pick_no=pick_no,
                projection=projection,
                acquired_by=acquired_by,
                given_by=given_by,
                need_positions=need_positions,
                adp_index=adp_index,
            )
        )

    for pick in review_acquires_picks:
        _append_pick(
            pick,
            acquired_by=review_name,
            given_by=other_name,
            need_positions=review_needs,
        )
    for pick in review_gives_picks:
        _append_pick(
            pick,
            acquired_by=other_name,
            given_by=review_name,
            need_positions=other_needs,
        )

    if not picks_in_trade:
        return None

    scoring = league_row.scoring_json or {}
    te_premium = float(scoring.get("bonus_rec_te") or 0)

    return {
        "season": ROOKIE_TRADE_SEASON,
        "draft_status": draft_status,
        "picks_made": picks_made,
        "te_premium": te_premium,
        "board_top": _board_top(state) if state is not None else board[:15],
        "picks_in_trade": picks_in_trade,
        "usage": (
            "Projected rookies at each traded pick slot — use when explaining why a "
            "manager trades up/down (e.g. 1.01 for Jeremiah Love vs giving 1.04/1.06 "
            "for Lemon + Sadiq in TEP)."
        ),
    }
