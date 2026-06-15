"""Deterministic tool DAGs for in-season advisor presets — LLM writes prose only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from backend.services.advisor_tools import AdvisorTools
from backend.services.rookie_draft_service import get_rookie_draft_view
from dynasty_draft.llm_advisor import build_inseason_advisor_context

HARNESS_PRESET_IDS = frozenset(
    {"suggest_trade", "trade_targets", "drop_candidates", "rookie_pick_prep"}
)

TOP_PACKAGES = 3
TOP_FA = 12
TOP_DROP_CANDIDATES = 10


def _compact_asset(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("player_id"):
        return {
            "name": row.get("name") or row.get("player_name"),
            "pos": row.get("position") or row.get("pos"),
            "ovr": row.get("ovr"),
            "tv": row.get("tv") or row.get("trade_value"),
            "tag": row.get("trade_tag"),
        }
    return {
        "pick": row.get("label")
        or f"{row.get('season')} R{row.get('round')}",
        "tv": row.get("trade_value") or row.get("tv"),
    }


def _compact_package(pkg: dict[str, Any]) -> dict[str, Any]:
    cp = pkg.get("counterparty") or {}
    return {
        "counterparty": cp.get("team_name"),
        "roster_id": cp.get("roster_id"),
        "direction": cp.get("direction"),
        "position_hook": cp.get("position_hook"),
        "give": [_compact_asset(p) for p in (pkg.get("give") or {}).get("players") or []]
        + [_compact_asset(p) for p in (pkg.get("give") or {}).get("picks") or []],
        "receive": [_compact_asset(p) for p in (pkg.get("receive") or {}).get("players") or []]
        + [_compact_asset(p) for p in (pkg.get("receive") or {}).get("picks") or []],
        "fairness": pkg.get("fairness"),
        "net_delta_adjusted_pct": pkg.get("net_delta_adjusted_pct"),
        "package_quality": pkg.get("package_quality"),
        "give_total_tv": pkg.get("give_total_tv"),
        "receive_total_tv": pkg.get("receive_total_tv"),
        "rationale": pkg.get("rationale"),
    }


def _compact_team(team: dict[str, Any]) -> dict[str, Any]:
    if team.get("error"):
        return team
    return {
        "team_name": team.get("team_name"),
        "roster_id": team.get("roster_id"),
        "contender_tier": team.get("contender_tier"),
        "dynasty_rank": team.get("dynasty_rank"),
        "avg_dynasty_rating": team.get("avg_dynasty_rating"),
        "starter_total_ppg": team.get("starter_total_ppg"),
        "needs": team.get("needs"),
        "surplus": team.get("surplus"),
        "starter_needs": team.get("starter_needs"),
        "trade_candidates": (team.get("trade_candidates") or [])[:6],
        "injuries": (team.get("injuries") or [])[:5],
    }


def _compact_rankings(rankings: dict[str, Any]) -> dict[str, Any]:
    def _top(rows: list[dict[str, Any]], n: int = 6) -> list[dict[str, Any]]:
        return [
            {
                "team": row.get("team") or row.get("team_name"),
                "roster_id": row.get("roster_id"),
                "avg_dynasty_rating": row.get("avg_dynasty_rating"),
                "contender_tier": row.get("contender_tier"),
                "dynasty_rank": row.get("dynasty_rank"),
            }
            for row in (rows or [])[:n]
        ]

    return {
        "by_dynasty_top": _top(rankings.get("by_dynasty") or []),
        "by_dynasty_bottom": _top(list(reversed(rankings.get("by_dynasty") or []))),
        "by_win_now_top": _top(rankings.get("by_win_now") or []),
    }


def _compact_fa_board(fa: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": row.get("name"),
            "pos": row.get("position"),
            "ovr": row.get("ovr"),
            "tv": row.get("tv"),
        }
        for row in (fa.get("players") or [])[:TOP_FA]
    ]


def _bench_drop_candidates(team: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for player in team.get("players") or []:
        tag = player.get("trade_tag")
        depth = player.get("depth_rank") or 99
        if tag == "core":
            continue
        if tag == "trade" or depth >= 3:
            rows.append(
                {
                    "name": player.get("name"),
                    "pos": player.get("position") or player.get("pos"),
                    "ovr": player.get("ovr"),
                    "tv": player.get("tv"),
                    "tag": tag,
                    "depth_rank": depth,
                }
            )
    rows.sort(key=lambda row: (row.get("ovr") or 0, row.get("depth_rank") or 0))
    return rows[:TOP_DROP_CANDIDATES]


def _compact_rookie_draft(view: Any | None) -> dict[str, Any] | None:
    if view is None:
        return None
    return {
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
            for row in view.bpa_top[:10]
        ],
        "board_top": [
            {
                "name": row.player_name,
                "pos": row.position,
                "ovr": row.ovr,
                "adp_pick": row.adp_pick,
            }
            for row in view.board[:12]
        ],
        "upcoming_pick_projections": [
            {
                "pick_no": row.pick_no,
                "team_name": row.team_name,
                "projected_rookie": {
                    "name": row.player_name,
                    "pos": row.position,
                    "ovr": row.ovr,
                },
            }
            for row in view.timeline
            if row.status == "projected" and row.player_name
        ][:12],
    }


def _advising_roster_id(focus_id: str) -> str:
    """Roster the user selected in the advisor From dropdown."""
    return str(focus_id)


def _suggest_trade_tool_params(
    tools: AdvisorTools,
    context: dict[str, Any],
    *,
    focus_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    # Proposer perspective is focus_id via AdvisorTools.proposer_roster_id.
    # target_roster_id is only for "trade with manager X" — never the advising team itself.
    target_roster_id = params.get("target_roster_id")
    if target_roster_id and str(target_roster_id) == str(focus_id):
        target_roster_id = None

    target_position = params.get("position")
    if target_position:
        target_position = str(target_position).upper()

    target_player_id = None
    player_query = params.get("player_query")
    if player_query:
        hits = tools.search_players(str(player_query)).get("hits") or []
        if hits:
            target_player_id = str(hits[0]["player_id"])

    return {
        "target_roster_id": str(target_roster_id) if target_roster_id else None,
        "target_player_id": target_player_id,
        "target_position": target_position,
    }


def _run_suggest_trade(
    tools: AdvisorTools,
    context: dict[str, Any],
    *,
    my_roster_id: str,
    focus_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    tool_params = _suggest_trade_tool_params(
        tools, context, focus_id=focus_id, params=params
    )
    result = tools.suggest_trades(
        target_roster_id=tool_params["target_roster_id"],
        target_player_id=tool_params["target_player_id"],
        target_position=tool_params["target_position"],
        rank_by_validation=False,
    )
    packages = result.get("packages") or []

    # Surplus hooks miss "I need a stud RB" style asks — scan the league by position.
    if (
        not packages
        and not tool_params["target_player_id"]
        and not tool_params["target_roster_id"]
    ):
        fallback_position = tool_params["target_position"]
        if not fallback_position:
            needs = (result.get("trade_surplus_summary") or {}).get("needs") or []
            if needs:
                fallback_position = str(needs[0].get("position") or "").upper() or None
        if fallback_position and fallback_position != tool_params["target_position"]:
            result = tools.suggest_trades(
                target_position=fallback_position,
                rank_by_validation=False,
            )
            packages = result.get("packages") or []
            tool_params = {**tool_params, "target_position": fallback_position}

    proposer_id = _advising_roster_id(focus_id)
    return {
        "proposer_roster_id": proposer_id,
        "advising_team": _compact_team(tools.get_team(proposer_id)),
        "target_roster_id": tool_params["target_roster_id"],
        "target_position": tool_params["target_position"],
        "target_player_id": tool_params["target_player_id"],
        "trade_surplus": result.get("trade_surplus_summary"),
        "packages": [_compact_package(pkg) for pkg in packages[:TOP_PACKAGES]],
        "package_count": len(packages),
    }


def _run_trade_targets(
    tools: AdvisorTools,
    context: dict[str, Any],
    *,
    my_roster_id: str,
    focus_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    proposer_id = _advising_roster_id(focus_id)
    rankings = tools.get_league_rankings()
    advising_team = tools.get_team(proposer_id)
    trades = tools.suggest_trades(rank_by_validation=False)
    packages = trades.get("packages") or []
    return {
        "proposer_roster_id": proposer_id,
        "league_rankings": _compact_rankings(rankings),
        "advising_team": _compact_team(advising_team),
        "trade_surplus": trades.get("trade_surplus_summary"),
        "packages": [_compact_package(pkg) for pkg in packages[:TOP_PACKAGES]],
        "package_count": len(packages),
    }


def _run_drop_candidates(
    tools: AdvisorTools,
    context: dict[str, Any],
    *,
    my_roster_id: str,
    focus_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    proposer_id = _advising_roster_id(focus_id)
    advising_team = tools.get_team(proposer_id)
    fa = tools.get_free_agents(limit=TOP_FA)
    return {
        "proposer_roster_id": proposer_id,
        "advising_team": _compact_team(advising_team),
        "bench_drop_candidates": _bench_drop_candidates(advising_team),
        "top_free_agents": _compact_fa_board(fa),
    }


def _run_rookie_pick_prep(
    tools: AdvisorTools,
    context: dict[str, Any],
    *,
    my_roster_id: str,
    focus_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    proposer_id = _advising_roster_id(focus_id)
    advising_team = tools.get_team(proposer_id)
    try:
        rookie_view = get_rookie_draft_view(
            tools.ctx.db, tools.ctx.league_id, roster_id=proposer_id
        )
    except (ValueError, FileNotFoundError):
        rookie_view = None
    return {
        "proposer_roster_id": proposer_id,
        "advising_team": _compact_team(advising_team),
        "rookie_draft": _compact_rookie_draft(rookie_view),
    }


def _run_waiver(
    tools: AdvisorTools,
    context: dict[str, Any],
    *,
    my_roster_id: str,
    focus_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    proposer_id = _advising_roster_id(focus_id)
    pos = params.get("position")
    if pos:
        pos = str(pos).upper()
    return {
        "proposer_roster_id": proposer_id,
        "advising_team": _compact_team(tools.get_team(proposer_id)),
        "free_agents": _compact_fa_board(
            tools.get_free_agents(position=pos, limit=TOP_FA)
        ),
        "position_filter": pos,
    }


def _run_player_lookup(
    tools: AdvisorTools,
    context: dict[str, Any],
    *,
    my_roster_id: str,
    focus_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    query = str(params.get("player_query") or "").strip()
    pos = params.get("position")
    if not query and (context.get("page_context") or {}).get("player_name"):
        query = str(context["page_context"]["player_name"])
    if not query:
        return {"error": "no player named in question"}
    search = tools.search_players(query, str(pos).upper() if pos else None)
    hits = search.get("hits") or []
    player_card: dict[str, Any] = {"error": "player not found"}
    if hits:
        player_card = tools.get_player(str(hits[0]["player_id"]))
    return {"search": {"query": query, "hits": hits[:5]}, "player": player_card}


def _run_team_review(
    tools: AdvisorTools,
    context: dict[str, Any],
    *,
    my_roster_id: str,
    focus_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    rid = str(params.get("roster_id") or focus_id)
    return {
        "team": _compact_team(tools.get_team(rid)),
        "league_rankings": _compact_rankings(tools.get_league_rankings()),
    }


def _run_news(
    tools: AdvisorTools,
    context: dict[str, Any],
    *,
    my_roster_id: str,
    focus_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    page = context.get("page_context") or {}
    query = (
        params.get("web_query")
        or params.get("player_query")
        or page.get("player_name")
        or "NFL injury report fantasy football"
    )
    result = tools.web_search(str(query))
    player: dict[str, Any] | None = None
    pname = params.get("player_query") or page.get("player_name")
    if pname:
        hits = tools.search_players(str(pname)).get("hits") or []
        if hits:
            player = tools.get_player(str(hits[0]["player_id"]))
    return {"web_search": result, "player_snapshot": player}


def _run_general(
    tools: AdvisorTools,
    context: dict[str, Any],
    *,
    my_roster_id: str,
    focus_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    return _run_team_review(
        tools,
        context,
        my_roster_id=my_roster_id,
        focus_id=focus_id,
        params={"roster_id": focus_id},
    )


_INTENT_RUNNERS = {
    "suggest_trade": _run_suggest_trade,
    "trade_targets": _run_trade_targets,
    "drop_candidates": _run_drop_candidates,
    "rookie_pick_prep": _run_rookie_pick_prep,
    "waiver": _run_waiver,
    "player_lookup": _run_player_lookup,
    "team_review": _run_team_review,
    "news": _run_news,
    "general": _run_general,
}


def run_intent_harness(
    intent: str,
    tools: AdvisorTools,
    context: dict[str, Any],
    *,
    my_roster_id: str,
    focus_id: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the fixed tool DAG for an intent; returns compact JSON for the LLM."""
    route_params = dict(params or {})
    runner = _INTENT_RUNNERS.get(intent) or _INTENT_RUNNERS["general"]
    resolved_intent = intent if intent in _INTENT_RUNNERS else "general"
    results = runner(
        tools,
        context,
        my_roster_id=my_roster_id,
        focus_id=focus_id,
        params=route_params,
    )
    return {
        "intent": resolved_intent,
        "harness": "intent_v1",
        "route": route_params.get("router"),
        "prose_tier": route_params.get("prose_tier"),
        "results": results,
    }


def run_preset_harness(
    prompt_id: str,
    tools: AdvisorTools,
    context: dict[str, Any],
    *,
    my_roster_id: str,
    focus_id: str,
) -> dict[str, Any]:
    """Execute the fixed tool DAG for a preset chip."""
    payload = run_intent_harness(
        prompt_id,
        tools,
        context,
        my_roster_id=my_roster_id,
        focus_id=focus_id,
        params={},
    )
    payload["preset_id"] = prompt_id
    return payload


def _trade_perspective_preamble(context: dict[str, Any]) -> str:
    focused = context.get("focused_team") or {}
    if not focused.get("viewing_opponent"):
        return ""
    team_name = focused.get("team_name") or "the selected team"
    roster_id = focused.get("roster_id") or "?"
    logged_in = (context.get("my_team") or {}).get("team_name") or "logged-in user"
    return (
        f"TRADE PERSPECTIVE: Advise as **{team_name}** (roster {roster_id}). "
        f"The logged-in user manages **{logged_in}** — do not recommend moves for "
        f"{logged_in}'s roster unless explicitly asked.\n\n"
    )


def harness_user_message(
    context: dict[str, Any],
    harness_payload: dict[str, Any],
    user_question: str,
) -> str:
    advisor_context = build_inseason_advisor_context(context)
    label = harness_payload.get("preset_id") or harness_payload.get("intent") or "advisor"
    question = user_question.strip() or "Answer using the pre-computed results."
    preamble = _trade_perspective_preamble(context)
    return f"""{preamble}Base context (JSON):
{json.dumps(advisor_context, indent=2, default=str)}

Pre-computed tool results for "{label}" (JSON):
{json.dumps(harness_payload, indent=2, default=str)}

Question:
{question}"""


def preset_harness_user_message(
    context: dict[str, Any],
    harness_payload: dict[str, Any],
    user_question: str,
) -> str:
    return harness_user_message(context, harness_payload, user_question)


def _preset_harness_system_prompt() -> str:
    return """You are an expert dynasty fantasy football in-season advisor for Dynasty Blackbook.

You receive pre-computed tool results in JSON. Do NOT invent players, rosters, trade values, or packages.
Use only data from base context and pre-computed results.

TRADE PERSPECTIVE:
- `trade_perspective` / `focused_team` is the team you advise FOR (From dropdown).
- `advising_team` and `proposer_roster_id` in tool results match that team.
- `my_team` is the logged-in user's Sleeper team only — ignore it for trades when `viewing_opponent` is true.

When relevant, structure your answer with:
- **Bottom line** — 2–3 sentence verdict
- **Top moves** — ranked actionable recommendations
- **Trade paths** / **Targets** / **Adds** — specific managers and players
- **Risks / watch-outs** — injuries, aging, roster holes

Name managers by team_name. Cite OVR and TV when comparing. Keep under 600 words unless the user asks for more."""


def stream_harness_advisor(
    context: dict[str, Any],
    harness_payload: dict[str, Any],
    api_key: str,
    *,
    user_question: str,
    model: str,
    feature: str = "advisor_preset",
) -> Iterator[str]:
    """Single streaming LLM call after deterministic harness."""
    from dynasty_draft.llm_advisor import DEFAULT_MODEL, stream_advisor_reply

    messages = [
        {
            "role": "user",
            "content": harness_user_message(context, harness_payload, user_question),
        }
    ]
    yield from stream_advisor_reply(
        api_key,
        provider="anthropic",
        model=model or DEFAULT_MODEL,
        messages=messages,
        system=_preset_harness_system_prompt(),
        feature=feature,
    )


def stream_preset_advisor(
    context: dict[str, Any],
    harness_payload: dict[str, Any],
    api_key: str,
    *,
    user_question: str,
    model: str,
) -> Iterator[str]:
    """Single streaming LLM call after deterministic preset harness."""
    yield "⏳ Loading league data…\n\n"
    yield from stream_harness_advisor(
        context,
        harness_payload,
        api_key,
        user_question=user_question,
        model=model,
        feature="advisor_preset",
    )

