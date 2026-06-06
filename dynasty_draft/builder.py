from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from dynasty_draft.draft_context import build_scoring_context
from dynasty_draft.dynasty_score import DynastyWeights
from dynasty_draft.projections import SleeperProjectionStore
from dynasty_draft.recommender import DraftState
from dynasty_draft.sleeper_client import SleeperClient
from dynasty_draft.strategy import DraftStrategy
from dynasty_draft.war_data import WarData


def resolve_draft_id(client: SleeperClient, config: dict[str, Any], user_id: str) -> str:
    draft_id = (config.get("draft_id") or "").strip()
    if draft_id:
        return draft_id
    league_id = (config.get("league_id") or "").strip()
    if league_id:
        league = client.get_league(league_id)
        if league.get("draft_id"):
            return str(league["draft_id"])
    season = str(config.get("season", "2026"))
    leagues = client.get_user_leagues(user_id, season=season)
    drafting = [
        lg for lg in leagues if lg.get("status") in {"pre_draft", "drafting"} and lg.get("draft_id")
    ]
    if len(drafting) == 1:
        return str(drafting[0]["draft_id"])
    if drafting:
        lines = ["Multiple active drafts found. Set draft_id or league_id in config.json:\n"]
        for league in drafting:
            lines.append(
                f"  - {league.get('name')} | league_id={league.get('league_id')} "
                f"| draft_id={league.get('draft_id')}"
            )
        raise RuntimeError("\n".join(lines))
    raise RuntimeError("No active draft found. Set draft_id or league_id in config.json.")


def build_state(config: dict[str, Any], *, exit_on_error: bool = True) -> DraftState:
    username = (config.get("sleeper_username") or "").strip()
    if not username:
        message = "Set sleeper_username in config.json (copy config.example.json)."
        if exit_on_error:
            print(message)
            sys.exit(1)
        raise RuntimeError(message)

    war_path = Path(config.get("war_csv", "war.csv"))
    if not war_path.exists():
        message = f"Missing WAR file: {war_path}"
        if exit_on_error:
            print(message)
            sys.exit(1)
        raise RuntimeError(message)

    client = SleeperClient()
    user = client.get_user(username)
    user_id = str(user["user_id"])
    try:
        draft_id = resolve_draft_id(client, config, user_id)
    except RuntimeError as exc:
        if exit_on_error:
            print(exc)
            sys.exit(1)
        raise

    draft = client.get_draft(draft_id)
    picks = client.get_draft_picks(draft_id)
    league = None
    league_users: list[dict[str, Any]] = []
    league_id = draft.get("league_id") or config.get("league_id")
    if league_id:
        league = client.get_league(str(league_id))
        league_users = client.get_league_users(str(league_id))
    players = client.get_players()
    war = WarData(war_path)
    strategy = DraftStrategy.from_config(config)

    state = DraftState(
        draft=draft,
        picks=picks,
        league=league,
        league_users=league_users,
        user_id=user_id,
        war=war,
        sleeper_players=players,
        trade_weight=float(config.get("trade_weight", 0.65)),
        worp_weight=float(config.get("worp_weight", 0.35)),
        dynasty_weights=DynastyWeights.from_config(config.get("dynasty_weights")),
        strategy=strategy,
    )

    try:
        scoring = build_scoring_context(state)
        state.projection_store = SleeperProjectionStore.load(
            client,
            season=str(config.get("season", "2026")),
            teams=state._teams(),
            roster_positions=state.roster_positions,
            superflex=state.is_superflex(),
            ppr=float(scoring.get("ppr", 0.5)),
            war=war,
            sleeper_players=players,
        )
    except Exception:
        state.projection_store = None

    return state
