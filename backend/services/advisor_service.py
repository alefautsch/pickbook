"""In-season AI advisor — assembles snapshot context for dynasty_draft/llm_advisor (Phase 8)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import League, PlayerSnapshot, Roster, RosterPlayer
from backend.services.league_context import build_league_scoring_context
from backend.services.portfolio_service import get_free_agents, get_portfolio
from backend.services.read_service import (
    get_league_analysis,
    get_league_detail,
    get_league_rankings,
    get_team_detail,
)
from backend.services.rookie_draft_service import get_rookie_draft_view
from backend.services.advisor_intent_router import stream_routed_advisor
from backend.services.advisor_preset_harness import (
    HARNESS_PRESET_IDS,
    run_preset_harness,
    stream_preset_advisor,
)
from backend.services.advisor_tools import (
    ADVISOR_TOOL_SPECS,
    AdvisorToolContext,
    AdvisorTools,
)
from dynasty_draft.llm_advisor import (
    ADVISOR_MODELS,
    DEFAULT_MODEL,
    INSEASON_ADVISOR_PROMPTS,
    advisor_model_by_id,
    inseason_prompt_by_id,
    stream_inseason_advisor,
)

_TOOL_PROVIDERS = frozenset({"anthropic"})


def _advisor_api_key(provider: str) -> str | None:
    settings = get_settings()
    if provider == "anthropic":
        return settings.anthropic_api_key
    if provider == "moonshot":
        return settings.moonshot_api_key
    return None


def _model_status_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in ADVISOR_MODELS:
        provider = model["provider"]
        rows.append(
            {
                "id": model["id"],
                "label": model["label"],
                "provider": provider,
                "available": bool(_advisor_api_key(provider)),
                "supports_tools": provider in _TOOL_PROVIDERS,
            }
        )
    return rows


def _default_model_id() -> str:
    for row in _model_status_rows():
        if row["available"]:
            return row["id"]
    return DEFAULT_MODEL

TOP_FA = 24
TOP_ROSTER_PLAYERS = 14
TOP_PORTFOLIO = 18


def _compact_player(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row.get("player_name") or row.get("name"),
        "pos": row.get("position") or row.get("pos"),
        "age": row.get("age"),
        "ovr": row.get("ovr") or row.get("dynasty_rating"),
        "hppg": row.get("hppg"),
        "worp_ppg": row.get("worp_ppg"),
        "tv": row.get("trade_value") or row.get("tv"),
        "injury": row.get("injury_status") or row.get("injury"),
        "expected": row.get("hppg_expected") or row.get("expected"),
        "win_now": row.get("win_now_rating"),
    }


def _player_from_snapshot(snap: PlayerSnapshot) -> dict[str, Any]:
    return _compact_player(
        {
            "player_name": snap.player_name,
            "position": snap.position,
            "age": snap.age,
            "dynasty_rating": snap.dynasty_rating,
            "hppg": snap.hppg,
            "worp_ppg": snap.worp_ppg,
            "trade_value": snap.trade_value,
            "injury_status": snap.injury_status,
            "hppg_expected": snap.hppg_expected,
            "win_now_rating": snap.win_now_rating,
        }
    )


def _rankings_summary(rankings) -> dict[str, list[dict[str, Any]]]:
    def _row(team: dict[str, Any]) -> dict[str, Any]:
        return {
            "team": team.get("team_name"),
            "roster_id": team.get("roster_id"),
            "is_me": team.get("is_me"),
            "avg_dynasty_rating": team.get("avg_dynasty_rating"),
            "starter_total_ppg": team.get("starter_total_ppg"),
            "total_trade_value": team.get("total_trade_value"),
            "draft_pick_value": team.get("draft_pick_value"),
            "dynasty_rank": team.get("dynasty_rank"),
            "starter_ppg_rank": team.get("starter_ppg_rank"),
            "tv_rank": team.get("tv_rank"),
            "win_rank": team.get("win_rank"),
            "contender_tier": team.get("contender_tier"),
            "contender_score": team.get("contender_score"),
        }

    return {
        "by_dynasty": [_row(t) for t in rankings.by_dynasty],
        "by_starter_ppg": [_row(t) for t in rankings.by_starter_ppg],
        "by_trade_value": [_row(t) for t in rankings.by_tv],
        "by_win_now": [_row(t) for t in rankings.by_win_now],
    }


def _starter_needs(team_detail) -> dict[str, int]:
    """Infer positional depth gaps from depth chart vs typical starter counts."""
    counts: dict[str, int] = defaultdict(int)
    for group in team_detail.depth_chart:
        counts[group.position] = len(group.players)

    needs: dict[str, int] = {}
    targets = {"QB": 2, "RB": 4, "WR": 5, "TE": 2}
    for pos, target in targets.items():
        gap = max(0, target - counts.get(pos, 0))
        if gap:
            needs[pos] = gap
    flex_depth = counts.get("RB", 0) + counts.get("WR", 0) + counts.get("TE", 0)
    needs["FLEX"] = max(0, 3 - flex_depth)
    return needs


def _league_team_rosters(
    db: Session,
    league_id: str,
    snapshots: dict[str, PlayerSnapshot],
) -> list[dict[str, Any]]:
    rosters = db.scalars(select(Roster).where(Roster.league_id == league_id)).all()
    teams: list[dict[str, Any]] = []
    for roster in sorted(rosters, key=lambda r: r.team_name or ""):
        player_rows: list[dict[str, Any]] = []
        rps = db.scalars(
            select(RosterPlayer).where(RosterPlayer.roster_id == roster.id)
        ).all()
        for rp in rps:
            snap = snapshots.get(rp.sleeper_player_id)
            if snap is None:
                continue
            player_rows.append(_player_from_snapshot(snap))
        player_rows.sort(key=lambda p: p.get("ovr") or 0, reverse=True)
        teams.append(
            {
                "team": roster.team_name,
                "roster_id": roster.sleeper_roster_id,
                "is_me": roster.is_me,
                "players": player_rows[:TOP_ROSTER_PLAYERS],
            }
        )
    return teams


def _portfolio_summary(db: Session, league_id: str) -> dict[str, Any]:
    portfolio = get_portfolio(db)
    multi = sorted(
        [h for h in portfolio.holdings if h.league_count >= 2],
        key=lambda h: (-h.league_count, -(max((lg.ovr or 0) for lg in h.leagues))),
    )[:TOP_PORTFOLIO]
    in_league = [
        h
        for h in portfolio.holdings
        if any(lg.league_id == league_id for lg in h.leagues)
    ]
    return {
        "total_leagues": portfolio.total_leagues,
        "unique_players": portfolio.unique_players,
        "multi_league_holdings": [
            {
                "name": h.player_name,
                "pos": h.position,
                "league_count": h.league_count,
                "exposure_flag": h.exposure_flag,
                "leagues": [
                    {"league": lg.league_name, "ovr": lg.ovr}
                    for lg in h.leagues
                ],
            }
            for h in multi
        ],
        "this_league_player_count": len(in_league),
        "by_position": [
            {"position": row.position, "holdings": row.holding_count}
            for row in portfolio.by_position
        ],
    }


def _rookie_draft_context(db: Session, league_id: str, roster_id: str | None) -> dict[str, Any] | None:
    try:
        view = get_rookie_draft_view(db, league_id, roster_id=roster_id)
    except (ValueError, FileNotFoundError):
        return None
    if view is None:
        return None
    return {
        "draft_id": view.draft_id,
        "draft_status": view.draft_status,
        "picks_made": view.picks_made,
        "total_picks": view.total_picks,
        "is_my_pick": view.is_my_pick,
        "starter_needs": view.starter_needs.model_dump(),
        "strategy_notes": view.strategy_notes,
        "bpa_top": [
            {
                "name": row.player_name,
                "pos": row.position,
                "ovr": row.ovr,
                "adp_pick": row.adp_pick,
                "bpa_rank": row.bpa_rank,
            }
            for row in view.bpa_top[:12]
        ],
        "need_top": [
            {
                "name": row.player_name,
                "pos": row.position,
                "ovr": row.ovr,
                "adp_pick": row.adp_pick,
                "need_rank": row.need_rank,
            }
            for row in view.need_top[:12]
        ],
        "value_pivot": view.value_pivot.model_dump(),
        "board_top": [
            {
                "name": row.player_name,
                "pos": row.position,
                "ovr": row.ovr,
                "adp_pick": row.adp_pick,
            }
            for row in view.board[:18]
        ],
        "upcoming_pick_projections": [
            {
                "pick_no": row.pick_no,
                "round": row.round,
                "team_name": row.team_name,
                "projected_rookie": {
                    "name": row.player_name,
                    "pos": row.position,
                    "ovr": row.ovr,
                },
            }
            for row in view.timeline
            if row.status == "projected" and row.player_name
        ][:15],
    }


def build_minimal_advisor_context(
    db: Session,
    league_id: str,
    *,
    focused_roster_id: str | None = None,
    page_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str, str]:
    """Small base context + my_roster_id and focused_roster_id for tools."""
    league = db.get(League, league_id)
    if league is None:
        raise ValueError(f"League {league_id} not found")

    my_roster = db.scalar(
        select(Roster).where(Roster.league_id == league_id, Roster.is_me.is_(True))
    )
    if my_roster is None:
        raise ValueError("No roster marked as yours in this league")

    focus_id = focused_roster_id or my_roster.sleeper_roster_id
    focus_roster = db.scalar(
        select(Roster).where(
            Roster.league_id == league_id,
            Roster.sleeper_roster_id == focus_id,
        )
    )
    if focus_roster is None:
        focus_id = my_roster.sleeper_roster_id
        focus_roster = my_roster

    team_detail = get_team_detail(db, league_id, focus_id)
    if team_detail is None:
        raise ValueError("Team snapshot not found — sync the league first")

    my_team_detail = (
        team_detail
        if focus_id == my_roster.sleeper_roster_id
        else get_team_detail(db, league_id, my_roster.sleeper_roster_id)
    )
    if my_team_detail is None:
        raise ValueError("Your team snapshot not found — sync the league first")

    scoring_ctx = build_league_scoring_context(league)

    return (
        {
            "league_id": league_id,
            "league_name": league.name,
            "season": league.season,
            "page_context": page_context,
            "focused_team": {
                "roster_id": team_detail.roster_id,
                "team_name": team_detail.team_name,
                "is_me": team_detail.is_me,
                "contender_tier": team_detail.contender_tier,
                "dynasty_rank": team_detail.dynasty_rank,
                "viewing_opponent": focus_id != my_roster.sleeper_roster_id,
            },
            "scoring": scoring_ctx.as_dict(),
            "my_team": {
                "team_name": my_team_detail.team_name,
                "roster_id": my_team_detail.roster_id,
                "dynasty_rank": my_team_detail.dynasty_rank,
                "contender_tier": my_team_detail.contender_tier,
                "avg_dynasty_rating": my_team_detail.avg_dynasty_rating,
                "starter_total_ppg": my_team_detail.starter_total_ppg,
                "total_trade_value": my_team_detail.total_trade_value,
                "draft_pick_value": my_team_detail.draft_pick_value,
            },
            "rookie_draft": _rookie_draft_context(db, league_id, focus_id),
        },
        my_roster.sleeper_roster_id,
        focus_id,
    )


def build_inseason_context(
    db: Session,
    league_id: str,
    *,
    focused_roster_id: str | None = None,
    page_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    league = db.get(League, league_id)
    if league is None:
        raise ValueError(f"League {league_id} not found")

    league_detail = get_league_detail(db, league_id)
    rankings = get_league_rankings(db, league_id)
    analysis = get_league_analysis(db, league_id)

    my_roster = db.scalar(
        select(Roster).where(Roster.league_id == league_id, Roster.is_me.is_(True))
    )
    if my_roster is None:
        raise ValueError("No roster marked as yours in this league")

    focus_id = focused_roster_id or my_roster.sleeper_roster_id
    focus_roster = db.scalar(
        select(Roster).where(
            Roster.league_id == league_id,
            Roster.sleeper_roster_id == focus_id,
        )
    )
    if focus_roster is None:
        focus_id = my_roster.sleeper_roster_id
        focus_roster = my_roster

    team_detail = get_team_detail(db, league_id, focus_id)
    if team_detail is None:
        raise ValueError("Team snapshot not found — sync the league first")

    my_team_detail = (
        team_detail
        if focus_id == my_roster.sleeper_roster_id
        else get_team_detail(db, league_id, my_roster.sleeper_roster_id)
    )
    if my_team_detail is None:
        raise ValueError("Your team snapshot not found — sync the league first")

    snapshots = {
        row.sleeper_player_id: row
        for row in db.scalars(
            select(PlayerSnapshot).where(PlayerSnapshot.league_id == league_id)
        ).all()
    }

    scoring_ctx = build_league_scoring_context(league)
    my_age = next(
        (p for p in (analysis.age_profiles or []) if p.roster_id == my_roster.sleeper_roster_id),
        None,
    )
    my_contender = None
    if analysis.contender_index:
        my_contender = next(
            (t for t in analysis.contender_index.teams if t.is_me),
            None,
        )

    fa_board = get_free_agents(db, league_id)
    free_agents = []
    if fa_board:
        free_agents = [
            _compact_player(row.model_dump())
            for row in fa_board.players[:TOP_FA]
        ]

    trade_surplus = None
    if analysis.trade_surplus:
        trade_surplus = analysis.trade_surplus.model_dump()

    return {
        "league_id": league_id,
        "league_name": league.name,
        "season": league.season,
        "snapshot_at": (
            rankings.computed_at.isoformat()
            if rankings and rankings.computed_at
            else datetime.now(timezone.utc).isoformat()
        ),
        "page_context": page_context,
        "focused_team": {
            "roster_id": team_detail.roster_id,
            "team_name": team_detail.team_name,
            "is_me": team_detail.is_me,
            "contender_tier": team_detail.contender_tier,
            "dynasty_rank": team_detail.dynasty_rank,
            "viewing_opponent": focus_id != my_roster.sleeper_roster_id,
        },
        "scoring": scoring_ctx.as_dict(),
        "my_team": {
            "team_name": my_team_detail.team_name,
            "roster_id": my_team_detail.roster_id,
            "dynasty_rank": my_team_detail.dynasty_rank,
            "starter_ppg_rank": my_team_detail.starter_ppg_rank,
            "tv_rank": my_team_detail.tv_rank,
            "avg_dynasty_rating": my_team_detail.avg_dynasty_rating,
            "starter_total_ppg": my_team_detail.starter_total_ppg,
            "total_trade_value": my_team_detail.total_trade_value,
            "draft_pick_value": my_team_detail.draft_pick_value,
            "contender_tier": my_team_detail.contender_tier,
            "contender_score": my_team_detail.contender_score,
            "traits": [t.model_dump() for t in my_team_detail.traits],
            "draft_picks": [p.model_dump() for p in my_team_detail.draft_picks],
        },
        "focused_roster": {
            "starters": [
                {
                    "slot": slot.slot,
                    **_compact_player(slot.player.model_dump() if slot.player else {}),
                }
                for slot in team_detail.starters
                if slot.player
            ],
            "bench": [_compact_player(p.model_dump()) for p in team_detail.bench],
            "injuries": [i.model_dump() for i in team_detail.injuries],
            "draft_picks": [p.model_dump() for p in team_detail.draft_picks],
        },
        "starter_needs": _starter_needs(team_detail),
        "league_rankings": _rankings_summary(rankings) if rankings else {},
        "league_team_rosters": _league_team_rosters(db, league_id, snapshots),
        "trade_surplus": trade_surplus,
        "age_profile": my_age.model_dump() if my_age else None,
        "contender_index": (
            {
                "tier": my_contender.tier,
                "composite_score": my_contender.composite_score,
                "contender_rank": my_contender.contender_rank,
                "inputs": my_contender.inputs.model_dump(),
            }
            if my_contender
            else None
        ),
        "portfolio": _portfolio_summary(db, league_id),
        "free_agents": free_agents,
        "rookie_draft": _rookie_draft_context(
            db, league_id, focus_id
        ),
    }


def advisor_status() -> dict[str, Any]:
    settings = get_settings()
    models = _model_status_rows()
    return {
        "configured": any(m["available"] for m in models),
        "web_search_configured": bool(settings.brave_api_key),
        "default_model": _default_model_id(),
        "models": models,
        "prompts": list(INSEASON_ADVISOR_PROMPTS),
    }


def stream_advisor_chat(
    db: Session,
    *,
    league_id: str,
    question: str = "",
    prompt_id: str | None = None,
    model_id: str = DEFAULT_MODEL,
    messages: list[dict[str, str]] | None = None,
    focused_roster_id: str | None = None,
    page_context: dict[str, Any] | None = None,
) -> Iterator[str]:
    row = advisor_model_by_id(model_id)
    api_key = _advisor_api_key(row["provider"])
    if not api_key:
        env_name = (
            "MOONSHOT_API_KEY"
            if row["provider"] == "moonshot"
            else "ANTHROPIC_API_KEY"
        )
        raise ValueError(
            f"{env_name} is not configured. Add it to .env to use {row['label']}."
        )

    user_question = question.strip()
    if prompt_id:
        preset = inseason_prompt_by_id(prompt_id)
        if preset is None:
            raise ValueError(f"Unknown prompt_id: {prompt_id}")
        if not user_question:
            user_question = preset["question"]

    context, my_roster_id, _focus_id = build_minimal_advisor_context(
        db,
        league_id,
        focused_roster_id=focused_roster_id,
        page_context=page_context,
    )

    advisor_tools = AdvisorTools(
        AdvisorToolContext(
            db=db,
            league_id=league_id,
            my_roster_id=my_roster_id,
            focused_roster_id=_focus_id,
        )
    )

    def dispatch_tool(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        return advisor_tools.dispatch(name, tool_input)

    tool_specs = ADVISOR_TOOL_SPECS if row["provider"] in _TOOL_PROVIDERS else None
    tool_dispatch = dispatch_tool if tool_specs else None

    use_harness = (
        prompt_id
        and not messages
        and prompt_id in HARNESS_PRESET_IDS
        and row["provider"] in _TOOL_PROVIDERS
    )
    if use_harness:
        harness_payload = run_preset_harness(
            prompt_id,
            advisor_tools,
            context,
            my_roster_id=my_roster_id,
            focus_id=_focus_id,
        )
        yield from stream_preset_advisor(
            context,
            harness_payload,
            api_key,
            user_question=user_question,
            model=row["model"],
        )
        return

    settings = get_settings()
    use_router = (
        row["provider"] in _TOOL_PROVIDERS
        and settings.llm_advisor_router_enabled
        and tool_dispatch is not None
    )
    if use_router:
        yield from stream_routed_advisor(
            context,
            advisor_tools,
            api_key,
            user_question=user_question,
            model=row["model"],
            my_roster_id=my_roster_id,
            focus_id=_focus_id,
        )
        return

    if messages:
        yield from stream_inseason_advisor(
            context,
            api_key,
            model=row["model"],
            messages=messages,
            tools=tool_specs,
            tool_handler=tool_dispatch,
        )
        return

    yield from stream_inseason_advisor(
        context,
        api_key,
        user_question=user_question,
        model=row["model"],
        tools=tool_specs,
        tool_handler=tool_dispatch,
    )
