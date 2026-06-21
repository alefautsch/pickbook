from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from dynasty_draft.draft_pick_ownership import build_pick_owner_index, collect_traded_picks
from dynasty_draft.draft_context import build_scoring_context
from dynasty_draft.external_adp import AdpStore
from dynasty_draft.dynasty_score import DynastyRatingCurve, DynastyWeights
from dynasty_draft.dynasty_dealer import load_dynasty_dealer_store
from dynasty_draft.ktc_values import KtcStore
from dynasty_draft.trade_value_blend import TradeValueBlend
from dynasty_draft.worp_blend import WorpBlend
from dynasty_draft.healthy_ppg import HealthyPpgStore
from dynasty_draft.projections import SleeperProjectionStore
from dynasty_draft.recommender import DraftState
from dynasty_draft.sleeper_client import SleeperClient
from dynasty_draft.strategy import DraftStrategy
from dynasty_draft.war_loader import load_war_data


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
    league_row_stub = None
    if league:
        league_row_stub = type(
            "LeagueStub",
            (),
            {
                "sleeper_league_id": str(league_id),
                "name": league.get("name") or "",
                "season": league.get("season") or config.get("season", "2026"),
                "total_rosters": league.get("total_rosters") or 12,
                "superflex": "SUPER_FLEX" in (league.get("roster_positions") or []),
                "scoring_json": league.get("scoring_settings") or {},
                "roster_positions_json": league.get("roster_positions") or [],
            },
        )()
    try:
        war, _war_meta = load_war_data(config, league_row=league_row_stub)
    except (FileNotFoundError, ValueError) as exc:
        message = str(exc)
        if exit_on_error:
            print(message)
            sys.exit(1)
        raise RuntimeError(message) from exc
    strategy = DraftStrategy.from_config(config)

    pick_owner_index = {}
    if league_id:
        pick_owner_index = build_pick_owner_index(collect_traded_picks(client, str(league_id)))

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
        dynasty_rating_curve=DynastyRatingCurve.from_config(config.get("dynasty_rating_curve")),
        strategy=strategy,
        pick_owner_index=pick_owner_index,
    )

    if config.get("ktc_enabled", True):
        try:
            state.ktc = KtcStore.load(superflex=state.is_superflex())
        except Exception:
            state.ktc = None
    force_metric_refresh = bool(config.get("_force_metric_refresh"))
    state.trade_blend = TradeValueBlend.from_config(config, ktc_available=state.ktc is not None)
    state.dealer = load_dynasty_dealer_store(
        config,
        superflex=state.is_superflex(),
        force_refresh=force_metric_refresh,
    )
    state.worp_blend = WorpBlend.from_config(config)
    try:
        state.adp_store = AdpStore.load(config, superflex=state.is_superflex())
    except Exception:
        state.adp_store = None

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
            force_refresh=force_metric_refresh,
        )
    except Exception:
        state.projection_store = None

    try:
        scoring = build_scoring_context(state)
        state.healthy_ppg_store = HealthyPpgStore.load(
            sleeper_players=players,
            war=war,
            teams=state._teams(),
            roster_positions=state.roster_positions,
            superflex=state.is_superflex(),
            ppr=float(scoring.get("ppr", 0.5)),
            force_refresh=force_metric_refresh,
        )
    except Exception:
        state.healthy_ppg_store = None

    return state
