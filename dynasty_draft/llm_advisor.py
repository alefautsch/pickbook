from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Literal

import anthropic
import requests

from dynasty_draft.draft_context import (
    build_league_team_rosters,
    build_scoring_context,
    league_rankings_summary,
)
from dynasty_draft.fall_analysis import build_fall_analysis
from dynasty_draft.pick_projector import project_next_picks
from dynasty_draft.pick_values import build_pick_trade_context
from dynasty_draft.recommender import DraftState

Provider = Literal["anthropic", "moonshot"]

DEFAULT_MODEL = "claude-sonnet-4-6"
MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"
RECENT_PICKS_LIMIT = 24
AVAILABLE_PER_POSITION = 12

ADVISOR_MODELS: list[dict[str, str]] = [
    {
        "id": "claude-sonnet-4-6",
        "label": "Claude Sonnet 4.6",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    },
    {
        "id": "kimi-k2.6",
        "label": "Kimi K2.6",
        "provider": "moonshot",
        "model": "kimi-k2.6",
    },
]


def advisor_model_by_id(model_id: str) -> dict[str, str]:
    for row in ADVISOR_MODELS:
        if row["id"] == model_id:
            return row
    return ADVISOR_MODELS[0]


def _recent_picks(state: DraftState, limit: int = RECENT_PICKS_LIMIT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    users_by_id = {str(u.get("user_id")): u for u in (state.league_users or [])}
    for pick in sorted(state.picks, key=lambda p: p.get("pick_no", 0))[-limit:]:
        meta = pick.get("metadata") or {}
        name = f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
        war = state.war.lookup(name) if name else None
        owner_id = str(pick.get("picked_by") or "")
        user = users_by_id.get(owner_id) or {}
        team_name = (user.get("metadata") or {}).get("team_name") or user.get("display_name")
        rows.append(
            {
                "pick_no": pick.get("pick_no"),
                "round": pick.get("round"),
                "team": team_name,
                "roster_id": pick.get("roster_id"),
                "name": war.name if war else name,
                "pos": meta.get("position"),
                "age": state._player_age(str(pick["player_id"])) if pick.get("player_id") else None,
                "trade_value": state.blended_trade_value(war) if war else None,
                "worp": war.worp if war else None,
            }
        )
    return rows


def _bookend_dynasty_targets(state: DraftState, *, per_pos: int = 6) -> dict[str, Any]:
    """Best available by dynasty OVR — primary lens for startup bookend advice."""
    info = state.next_pick_info()
    bookend = info.get("consecutive_picks") or []
    pool = state.available_players()
    if not pool:
        return {"pick_numbers": bookend, "top_by_dynasty_rating": [], "by_position": {}}

    dynasty = state.dynasty_scores(pool)
    rows: list[dict[str, Any]] = []
    for player_id, player in pool:
        scored = dynasty.get(player_id) or {}
        blended = state.with_blended_tv(player)
        eff_worp, worp_proj = state._effective_worp(player_id, blended)
        rows.append(
            {
                "name": player.name,
                "pos": player.pos,
                "age": scored.get("age"),
                "dynasty_rating": scored.get("dynasty_rating"),
                "dynasty_score": scored.get("dynasty_score"),
                "dynasty_components": scored.get("dynasty_components"),
                "trade_value": state.blended_trade_value(player),
                "effective_worp": eff_worp,
                "worp_uses_projection": worp_proj,
                "adp_pick": state._adp_index().pick_no(player.name),
            }
        )

    by_dynasty = sorted(rows, key=lambda row: row.get("dynasty_rating") or 0, reverse=True)
    by_pos: dict[str, list[dict[str, Any]]] = {}
    for pos in ("QB", "RB", "WR", "TE"):
        by_pos[pos] = [row for row in by_dynasty if row["pos"] == pos][:per_pos]

    return {
        "pick_numbers": bookend,
        "top_by_dynasty_rating": by_dynasty[:18],
        "by_position": by_pos,
        "note": (
            "Primary startup bookend targets. Prefer high dynasty_rating + youth at QB in superflex. "
            "Override pick_projection / falls_to_you sim when they disagree."
        ),
    }


def _advisor_decision_framework(state: DraftState) -> dict[str, Any]:
    return {
        "primary_lens": "dynasty_rating (50–99) for startup dynasty builds",
        "secondary": ["effective_worp (WORP*)", "blended trade_value", "age", "starter_needs", "adp_delta"],
        "sim_boards_are_not_recommendations": True,
        "pick_fit_score_weights": {
            "trade_value": state.trade_weight,
            "worp": state.worp_weight,
            "note": "Used in UI `score` for pick-fit ranking — advisor should still lead with dynasty_rating.",
        },
        "dynasty_rating_formula": {
            "tv": state.dynasty_weights.tv if state.dynasty_weights else 0.45,
            "worp": state.dynasty_weights.worp if state.dynasty_weights else 0.25,
            "upside": state.dynasty_weights.upside if state.dynasty_weights else 0.15,
            "age": state.dynasty_weights.age if state.dynasty_weights else 0.10,
            "trajectory": state.dynasty_weights.trajectory if state.dynasty_weights else 0.05,
        },
        "qb_startup_rule": (
            "In superflex startup, favor younger QBs with higher dynasty_rating over "
            "win-now veterans with higher raw TV/historical WORP (e.g. prefer Trevor Lawrence "
            "profile over Dak Prescott profile when both are realistic targets)."
        ),
    }


def _bookend_plan_summary(state: DraftState) -> dict[str, Any]:
    proj = project_next_picks(state)
    current = proj.get("current_bookend") or {}
    nxt = proj.get("next_bookend") or {}
    between = proj.get("between_bookends") or {}
    return {
        "picks_before_current_bookend": current.get("picks_before") or [],
        "current_bookend_picks": current.get("pick_numbers") or [],
        "current_planned_pair": current.get("planned_picks") or [],
        "between_bookends": between.get("projected_picks") or [],
        "next_bookend_picks": nxt.get("pick_numbers") or [],
        "next_planned_pair": nxt.get("planned_picks") or [],
        "targets_at_next_bookend": nxt.get("targets_at_bookend") or [],
        "likely_gone_before_next_bookend": between.get("likely_off_board") or [],
    }


def _metric_definitions() -> dict[str, str]:
    return {
        "trade_value": "Blended dynasty market capital (dynasty-daddy + KeepTradeCut). Higher = more dynasty trade demand.",
        "worp": "Dynasty-daddy historical WORP (backward-looking production). Shown in UI when blend equals history.",
        "projected_worp": "Blended effective WORP when projection contributes: α×historical + (1−α)×Sleeper VOR→WORP. α rises with years_exp (rookies ~0% hist, vets ~75–88%).",
        "dynasty_rating": "50–99 display rating from dynasty_score (raw 0–1 composite) via a fixed-board curve — elites land mid/high 90s. Raw formula: 45% TV + 25% proj WORP + 15% ceiling + 10% age + 5% trajectory.",
        "dynasty_score": "Raw 0–1 dynasty composite before the display curve; use for precise comparisons.",
        "dynasty_rookie": "True when rating is a rookie projection (no historical WORP in war.csv). Shown as N* in UI.",
        "dynasty_components": "Normalized 0–1 breakdown: tv, worp, upside, age, trajectory for each player.",
        "avg_dynasty_rating": "Team roster average dynasty_rating (50–99). Primary sort for league_rankings.by_dynasty.",
        "starter_avg_dynasty_rating": "Average dynasty_rating of optimal starters only.",
        "score": "UI pick-fit rank (TV + WORP weights + roster needs). Secondary to dynasty_rating for startup advice.",
        "effective_worp": "Blended historical + Sleeper projection (WORP* in UI). Key dynasty_rating input.",
        "adp_pick": "Consensus draft slot from trade-value rank. Lower = goes earlier (ADP 12 ≈ pick 12).",
        "adp_delta": "your_pick - adp_pick. Positive = value (player fell to you). Negative = reach (you draft them early).",
        "falls_to_you": "TV-heavy sim of who might be on the board at each bookend pick. Use top_by_dynasty_rating inside it for WHO TO DRAFT — not top_available_sim.",
        "bookend_dynasty_targets": "Best available ranked by dynasty_rating (age + proj WORP + TV + ceiling). Primary bookend pick list.",
        "pick_projection": "Bookend-centric draft sim: picks_before on current_bookend (now→your bookend), your planned pair, between bookends, next bookend.",
    }


def build_advisor_context(
    state: DraftState,
    *,
    per_position: int = AVAILABLE_PER_POSITION,
) -> dict[str, Any]:
    info = state.next_pick_info()
    streak = state.consecutive_pick_numbers()
    league = state.league or {}
    return {
        "draft_name": (state.draft.get("metadata") or {}).get("name") or "Draft",
        "draft_status": state.draft.get("status"),
        "scoring": build_scoring_context(state),
        "draft_phase": state.strategy.draft_phase,
        "teams": int((state.draft.get("settings") or {}).get("teams", state.strategy.teams)),
        "rounds": int((state.draft.get("settings") or {}).get("rounds", 20)),
        "my_slot": state.my_slot,
        "picks_made": len(state.picks),
        "next_pick": info.get("pick_no"),
        "on_clock": info.get("is_my_pick"),
        "picks_until_mine": info.get("picks_until_mine"),
        "consecutive_pick_numbers": streak,
        "back_to_back": len(streak) >= 2,
        "upcoming_pick_path": info.get("my_upcoming"),
        "strategy_notes": state.strategy.strategy_notes(
            state.war, tv_fn=state.blended_trade_value
        ),
        "reserved_rookies": state.strategy.reserved_players(
            state.war, tv_fn=state.blended_trade_value
        ),
        "trade_value_blend": {
            "dd_weight": state.trade_blend.dd_weight,
            "ktc_weight": state.trade_blend.ktc_weight,
        },
        "worp_blend": {
            "historical_weight": state.worp_blend.historical_weight,
            "projected_weight": state.worp_blend.projected_weight,
            "auto_adjust_by_experience": state.worp_blend.auto_adjust_by_experience,
        },
        "my_roster": state.roster_summary(),
        "starter_needs": state.starter_needs(),
        "league_team_rosters": build_league_team_rosters(state),
        "league_rankings": league_rankings_summary(state),
        "available_by_position": state.recommend_by_position(per_pos=per_position),
        "pick_projection": project_next_picks(state),
        "bookend_plan": _bookend_plan_summary(state),
        "decision_framework": _advisor_decision_framework(state),
        "bookend_dynasty_targets": _bookend_dynasty_targets(state),
        "top_recommendations": state.recommend(limit=12),
        "falls_to_you": build_fall_analysis(state),
        "pick_trade_analysis": build_pick_trade_context(state),
        "tier_cliffs": state.tier_cliffs(),
        "recent_draft_picks": _recent_picks(state),
        "trade_weight": state.trade_weight,
        "worp_weight": state.worp_weight,
        "dynasty_weights": {
            "tv": state.dynasty_weights.tv if state.dynasty_weights else 0.45,
            "worp": state.dynasty_weights.worp if state.dynasty_weights else 0.25,
            "upside": state.dynasty_weights.upside if state.dynasty_weights else 0.15,
            "age": state.dynasty_weights.age if state.dynasty_weights else 0.10,
            "trajectory": state.dynasty_weights.trajectory if state.dynasty_weights else 0.05,
        },
        "metric_definitions": _metric_definitions(),
        "projection_source": (
            {
                "provider": "sleeper",
                "season": state.projection_store.season,
                "ppr": state.projection_store.ppr,
            }
            if state.projection_store
            else {"provider": "imputed_only"}
        ),
        "league_name": league.get("name"),
    }


def _system_prompt() -> str:
    return """You are an expert dynasty fantasy football draft advisor.

Read `metric_definitions` and `decision_framework` in the context JSON.

STARTUP DYNASTY PRIORITY (follow this order):
1. **`bookend_dynasty_targets`** + **`dynasty_rating` (50–99)** — PRIMARY. Includes age, blended WORP, TV, ceiling, trajectory.
2. **`top_recommendations`** / **`available_by_position`** — curated lists with dynasty_rating, WORP*, TV, ADP.
3. **`starter_needs`** + **`effective_worp`** — roster holes and projection-aware production.
4. **`adp_delta`** — reach vs value (your_pick - adp; positive = fell to you, negative = reach).
5. **`falls_to_you` / `pick_projection` sim boards** — ONLY who might be ON the board. TV-heavy sim over-ranks aging vets (Dak). **Never recommend someone just because they top `top_available_sim`.** Use `top_by_dynasty_rating` inside falls_to_you instead.

Superflex startup QB rule: prefer younger QBs with higher dynasty_rating (e.g. Trevor Lawrence profile) over older win-now QBs (Dak) when both are realistic — unless user explicitly wants win-now.

`score` in context uses `decision_framework.pick_fit_score_weights` for UI pick-fit — secondary to dynasty_rating for your advice.
Think in BOOKEND PAIRS — the current snake turn AND the next one.

When they have back-to-back picks, always cover:
1) Best single pick right now (pick 1 of the pair)
2) Pairing plan for both picks (e.g. QB + WR, elite WR + value TE)
3) Fallback if pick 1 is gone before pick 2
4) One contrarian but defensible alternative

Required sections in every answer:
- **This bookend (picks X & Y)** — your two-pick plan now
- **Don't wait on** — players likely gone before your NEXT bookend
- **Targets at your NEXT bookend** — who to plan for at picks A & B based on projection
- **Bridge strategy** — what roster hole the current pair sets up for the next bookend

Use `bookend_dynasty_targets` first, then `pick_projection` / `bookend_plan` / `falls_to_you`:
- `bookend_dynasty_targets.by_position` — who you should actually consider at this bookend (dynasty-ranked)
- `falls_to_you.at_each_pick.top_by_dynasty_rating` — dynasty-ranked board at each pick (prefer over `top_available_sim`)
- `falls_to_you.at_each_pick.top_available_sim` — who the TV sim thinks is left (informational only)
- `falls_to_you.next_bookend` — same split for your NEXT bookend turn
- Reject sim-default pairs like Dak + Loveland when dynasty targets favor younger QBs or better long-term pairings
- `effective_worp` / WORP* blends historical + Sleeper projection — key dynasty_rating input
- `bookend_plan.picks_before_current_bookend` — sim of every pick BEFORE their current bookend (the gap while they wait)
- `current_bookend.planned_picks` — projection assumes they take this pair NOW (align with or refine this)
- `bookend_plan.between_bookends` — simulated league picks after current bookend until next bookend
- `next_bookend.planned_picks` — projected pair at the following bookend
- `next_bookend.targets_at_bookend` — best available if plans change
- `bookend_plan.likely_gone_before_next_bookend` — do NOT tell them to wait on these

ADP (lower pick # = goes earlier):
- At YOUR pick 31, a player with ADP 54 is a REACH (you take them ~23 picks before consensus).
- At YOUR pick 31, ADP 20 is VALUE (they fell ~11 picks to you).
- `adp_delta` = your_pick - adp_pick (positive = steal/value, negative = reach). Do NOT call high ADP at an early pick a steal.

Startup PICK-POSITION trades (not player trades):
- Use `pick_trade_analysis.my_future_pick_values` — projected player + TV at each of your remaining picks
- `pick_trade_analysis.example_swaps` shows 2-for-2 bookend-for-spread math (e.g. 2.01+8.01 ↔ 3.01+5.01)
- Trades are almost always even pick counts (2-for-2). Compare `give_total_tv` vs `receive_total_tv`
- Bookend pairs are valuable; swapping them spreads picks through a round — good if you hate the bookend targets (e.g. QB run at 1.11)
- When user asks about trading picks, evaluate net TV AND roster fit (superflex QB timing, avoiding Caleb if that's the projection)

Use the full league context:
- `league_rankings.by_dynasty`: team standings by avg_dynasty_rating (50–99) — use when comparing roster builds
- `league_rankings.by_trade_value` / `by_win_now`: market TV and win-now standings
- `league_team_rosters`: every manager's picks — infer tendencies (QB early, RB heavy, etc.)
- `available_by_position`: top 12 available per position with `dynasty_rating` per player
- `recent_draft_picks`: last 24 picks with team names
- `scoring`: league scoring rules (PPR, superflex, TD bonuses)

Account for:
- Vet-only startup vs separate reversed rookie draft
- Reserved rookies (already penciled in — don't recommend vet RB early if Love is reserved)
- Superflex / 2QB leagues (QB premium is real)
- Tier cliffs in the data

On follow-up messages, stay concise and reference prior advice when helpful.
Format with clear headings. Keep under 800 words unless the decision is complex."""


def build_followup_context_snippet(state: DraftState) -> str:
    """Compact live context for follow-up turns (full JSON only on first message)."""
    info = state.next_pick_info()
    fall = build_fall_analysis(state)
    proj = project_next_picks(state)
    before = (proj.get("current_bookend") or {}).get("picks_before") or []
    lines = [
        f"[Live update — overall pick #{info.get('pick_no')}, {len(state.picks)} picks made]",
    ]
    if before:
        names = ", ".join(f"{row['name']}" for row in before[:6])
        cur = (proj.get("current_bookend") or {}).get("pick_numbers") or []
        cur_lbl = f"#{cur[0]}" + (f" & #{cur[1]}" if len(cur) > 1 else "") if cur else "?"
        lines.append(f"Before your bookend ({len(before)} picks → {cur_lbl}): {names}")
    for block in fall.get("at_each_pick") or []:
        pick_no = block.get("pick_no")
        dyn_top = ", ".join(
            f"{row['name']} (Dyn {row.get('dynasty_rating', '?')})"
            for row in (block.get("top_by_dynasty_rating") or [])[:5]
        )
        lines.append(f"Dynasty targets at #{pick_no}: {dyn_top or '—'}")
        sim_top = ", ".join(
            f"{row['name']}" for row in (block.get("top_available_sim") or [])[:3]
        )
        if sim_top:
            lines.append(f"  (TV sim board: {sim_top} — informational only)")
        fallers = block.get("likely_fallers") or []
        if fallers:
            lines.append(
                "Likely fallers: "
                + ", ".join(f"{row['name']}" for row in fallers[:5])
            )
    next_blocks = fall.get("next_bookend") or []
    if next_blocks:
        nb = next_blocks[0]
        top = ", ".join(
            f"{row['name']}" for row in (nb.get("top_available_sim") or [])[:4]
        )
        lines.append(f"Next bookend #{nb.get('pick_no')}: {top or '—'}")
    return "\n".join(lines)


def build_initial_user_message(context: dict[str, Any], user_question: str) -> str:
    payload = json.dumps(context, indent=2, default=str)
    question = user_question.strip() or (
        "I'm at the bookend with two picks in a row. What should I take with each pick "
        "and what pairings maximize trade value + winning?"
    )
    return f"""Draft context (JSON):
{payload}

Question:
{question}"""


def _stream_anthropic(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int = 2500,
) -> Iterator[str]:
    client = anthropic.Anthropic(api_key=api_key.strip())
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=_system_prompt(),
        messages=messages,
    ) as stream:
        yield from stream.text_stream


def _stream_moonshot(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int = 2500,
) -> Iterator[str]:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": _system_prompt()}, *messages],
        "max_tokens": max_tokens,
        "stream": True,
        "temperature": 0.6,
        "thinking": {"type": "disabled"},
    }
    response = requests.post(
        f"{MOONSHOT_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        },
        json=payload,
        stream=True,
        timeout=180,
    )
    response.raise_for_status()
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data = line[6:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        text = delta.get("content")
        if text:
            yield text


def stream_advisor_reply(
    api_key: str,
    *,
    provider: Provider,
    model: str,
    messages: list[dict[str, str]],
) -> Iterator[str]:
    if not api_key.strip():
        raise ValueError("API key is required for the selected advisor.")

    if not messages or messages[-1]["role"] != "user":
        raise ValueError("Last message must be from the user.")

    if provider == "anthropic":
        yield from _stream_anthropic(api_key=api_key, model=model, messages=messages)
        return
    if provider == "moonshot":
        yield from _stream_moonshot(api_key=api_key, model=model, messages=messages)
        return
    raise ValueError(f"Unsupported provider: {provider}")


def stream_evaluate_picks(
    state: DraftState,
    api_key: str,
    *,
    user_question: str = "",
    model: str = DEFAULT_MODEL,
    per_position: int = AVAILABLE_PER_POSITION,
) -> Iterator[str]:
    """Single-turn helper (CLI / legacy)."""
    row = advisor_model_by_id(model)
    context = build_advisor_context(state, per_position=per_position)
    yield from stream_advisor_reply(
        api_key,
        provider=row["provider"],  # type: ignore[arg-type]
        model=row["model"],
        messages=[
            {
                "role": "user",
                "content": build_initial_user_message(context, user_question),
            }
        ],
    )


def evaluate_picks(
    state: DraftState,
    api_key: str,
    *,
    user_question: str = "",
    model: str = DEFAULT_MODEL,
    per_position: int = AVAILABLE_PER_POSITION,
) -> str:
    return "".join(
        stream_evaluate_picks(
            state,
            api_key,
            user_question=user_question,
            model=model,
            per_position=per_position,
        )
    )
