from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Literal

import anthropic
import requests

from backend.services.llm_usage import create_message, stream_message

from dynasty_draft.draft_context import (
    build_league_team_rosters,
    build_scoring_context,
    league_rankings_summary,
)
from dynasty_draft.fall_analysis import build_fall_analysis
from dynasty_draft.pick_projector import project_next_picks
from dynasty_draft.pick_values import _simulate_through, build_pick_trade_context
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
    """Best projected-at-bookend options by dynasty OVR."""
    info = state.next_pick_info()
    bookend = info.get("consecutive_picks") or []
    target_pick = bookend[0] if bookend else info.get("pick_no")
    pool = _simulate_through(state, int(target_pick)) if target_pick else state.available_players()
    current_pool = state.available_players()
    if not pool:
        return {"pick_numbers": bookend, "top_by_dynasty_rating": [], "by_position": {}}

    dynasty = state.dynasty_scores(pool)
    current_dynasty = state.dynasty_scores(current_pool)

    def _rows(source_pool: list[tuple[str, Any]], scores: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for player_id, player in source_pool:
            scored = scores.get(player_id) or {}
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
        return sorted(rows, key=lambda row: row.get("dynasty_rating") or 0, reverse=True)

    by_dynasty = _rows(pool, dynasty)
    current_by_dynasty = _rows(current_pool, current_dynasty)
    by_pos: dict[str, list[dict[str, Any]]] = {}
    for pos in ("QB", "RB", "WR", "TE"):
        by_pos[pos] = [row for row in by_dynasty if row["pos"] == pos][:per_pos]

    return {
        "pick_numbers": bookend,
        "projected_at_pick": target_pick,
        "top_by_dynasty_rating": by_dynasty[:18],
        "by_position": by_pos,
        "if_they_fall_from_current_board": current_by_dynasty[:12],
        "note": (
            "Primary startup bookend targets are projected at the first bookend pick. "
            "Use if_they_fall_from_current_board only as live-board contingency if the sim was too aggressive."
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
        "value_based_drafting": {
            "primary_ranking": "bpa_recommendations (cross-position VOR + dynasty + ADP value bonus)",
            "need_ranking": "need_adjusted_recommendations (legacy pick-fit with starter-need nudges)",
            "value_override_adp_delta": 6,
            "rule": (
                "When adp_delta >= 6 OR a player is in value_pivot.take_bpa_over_need, take BPA "
                "and note the trade-market path to fill the roster hole later. "
                "When value_pivot.wait_for_later is non-empty, do NOT recommend reaching — "
                "their ADP aligns with a future bookend pick. starter_needs is a tiebreaker "
                "when BPA and need-adjusted disagree by less than one tier (~3 dynasty points)."
            ),
        },
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
        "trade_value": "Blended dynasty market capital (50% Dynasty Dealer trade-derived + 25% Dynasty Daddy + 25% KTC when available). Feeds ~37% of dynasty OVR.",
        "worp": "Dynasty-daddy historical WORP (backward-looking production). Shown in UI when blend equals history.",
        "projected_worp": "Blended effective WORP when projection contributes: α×historical + (1−α)×Sleeper VOR→WORP. α rises with years_exp (rookies ~0% hist, vets ~75–88%).",
        "dynasty_rating": "50–99 display rating from dynasty_score (raw 0–1 composite) via a fixed-board curve — elites land mid/high 90s. Raw formula: 37% TV + 33% proj WORP + 15% ceiling + 10% age + 5% trajectory.",
        "dynasty_score": "Raw 0–1 dynasty composite before the display curve; use for precise comparisons.",
        "dynasty_rookie": "True when rating is a rookie projection (no historical WORP in war.csv). Shown as N* in UI.",
        "dynasty_components": "Normalized 0–1 breakdown: tv, worp (blended with per-game W/g+HPPG when available; QBs use replacement-relative PPG), upside, age, trajectory.",
        "avg_dynasty_rating": "Team roster average dynasty_rating (50–99). Primary sort for league_rankings.by_dynasty.",
        "starter_avg_dynasty_rating": "Average dynasty_rating of optimal starters only.",
        "starter_total_ppg": "Sum of healthy/expected PPG across optimal starters (nflverse or Sleeper/TV imputation).",
        "starter_ppg_rank": "League rank by starter_total_ppg (higher = more weekly scoring from starters).",
        "hppg_expected": "True when HPPG is projected (rookie/no nflverse history) rather than snap-filtered actuals.",
        "score": "UI need-adjusted pick-fit rank (TV + WORP + roster needs). Use bpa_recommendations for true BPA/VBD.",
        "bpa_score": "Cross-position value rank: VOR + dynasty_rating + ADP fall bonus; ignores roster holes.",
        "value_pivot": "Players where BPA rank beats need-adjusted rank — take value, trade surplus later.",
        "wait_for_later": "Elite players whose ADP matches a future pick — do not reach early; wait for that bookend.",
        "effective_worp": "Blended historical + Sleeper projection (WORP* in UI). Key dynasty_rating input.",
        "adp_pick": "Consensus draft slot from external ADP when loaded (Sleeper / BeatADP / DLF / CSV), else trade-value rank. Lower = goes earlier.",
        "adp_delta": "your_pick - adp_pick. Positive = value (player fell to you). Negative = reach (you draft them early).",
        "falls_to_you": "TV-heavy sim of who might be on the board at each bookend pick. Use top_by_dynasty_rating inside it for WHO TO DRAFT — not top_available_sim.",
        "bookend_dynasty_targets": "Best projected-at-bookend players ranked by dynasty_rating (age + proj WORP + TV + ceiling). Primary bookend pick list; if_they_fall_from_current_board is contingency only.",
        "pick_projection": "Bookend-centric draft sim: league picks are TV/needs-based; your planned pairs and next-bookend targets are dynasty_rating-first.",
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
        "trade_value_blend": {
            "dd_weight": state.trade_blend.dd_weight,
            "ktc_weight": state.trade_blend.ktc_weight,
            "dealer_weight": state.trade_blend.dealer_weight,
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
        "bpa_by_position": state.bpa_by_position(per_pos=per_position),
        "pick_projection": project_next_picks(state),
        "bookend_plan": _bookend_plan_summary(state),
        "decision_framework": _advisor_decision_framework(state),
        "bookend_dynasty_targets": _bookend_dynasty_targets(state),
        "bpa_recommendations": state.bpa_recommendations(limit=12),
        "need_adjusted_recommendations": state.recommend(limit=12),
        "value_pivot": state.value_pivot_summary(limit=8),
        "top_recommendations": state.recommend(limit=12),
        "falls_to_you": build_fall_analysis(state),
        "pick_trade_analysis": build_pick_trade_context(state),
        "tier_cliffs": state.tier_cliffs(),
        "recent_draft_picks": _recent_picks(state),
        "trade_weight": state.trade_weight,
        "worp_weight": state.worp_weight,
        "adp_source": state._adp_index().source_label,
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
1. **`bookend_dynasty_targets.top_by_dynasty_rating`** + **`dynasty_rating` (50–99)** — PRIMARY. This is projected at their actual bookend, not merely the current board.
2. **`bpa_recommendations`** + **`value_pivot.take_bpa_over_need`** — VALUE-BASED DRAFTING. Cross-position BPA; when ADP value is large or BPA beats need-adjusted, take the player and trade surplus later.
3. **`need_adjusted_recommendations`** / **`available_by_position`** — need-adjusted pick-fit; tiebreaker only when value gap is small.
4. **`starter_needs`** — roster holes; do NOT force-fill at the expense of clear BPA/ADP value (adp_delta >= 6).
5. **`adp_delta`** — reach vs value (your_pick - adp; positive = fell to you, negative = reach).
6. **`falls_to_you` / `pick_projection` sim boards** — ONLY who might be ON the board. TV-heavy sim over-ranks aging vets (Dak). **Never recommend someone just because they top `top_available_sim`.** Use `top_by_dynasty_rating` inside falls_to_you instead.

Superflex startup QB rule: prefer younger QBs with higher dynasty_rating (e.g. Trevor Lawrence profile) over older win-now QBs (Dak) when both are realistic — unless user explicitly wants win-now.

`score` in context is need-adjusted pick-fit — secondary to `bpa_recommendations` when value_pivot flags a player.
Think in BOOKEND PAIRS — the current snake turn AND the next one.

VALUE-BASED DRAFTING (dynasty trade market):
- Compare `bpa_recommendations` vs `need_adjusted_recommendations` side by side.
- If `value_pivot.take_bpa_over_need` is non-empty OR adp_delta >= 6: **take BPA**, explain how to fill the hole via trade or next bookend.
- If `value_pivot.wait_for_later` is non-empty: **do NOT reach** — ADP aligns with a future pick (e.g. ADP 50 at pick 30 when pick 50 is next bookend). Wait and fill need now.
- Negative adp_delta = reach. High dynasty_rating alone does NOT justify a reach.
- Example: elite RB/WR falls 8+ picks (positive adp_delta) while you need QB/TE — draft the value, trade later.
- Need-fill is a tiebreaker when BPA and need-adjusted are within ~3 dynasty_rating points, not an override.

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
- `bookend_dynasty_targets.if_they_fall_from_current_board` — conditional only; mention elite fall-throughs, but do not lead with them as the base plan if projected gone before their pick
- `falls_to_you.at_each_pick.top_by_dynasty_rating` — dynasty-ranked board at each pick (prefer over `top_available_sim`)
- `falls_to_you.at_each_pick.top_available_sim` — who the TV sim thinks is left (informational only)
- `falls_to_you.next_bookend` — same split for your NEXT bookend turn
- Reject sim-default pairs like Dak + Loveland when dynasty targets favor younger QBs or better long-term pairings
- `effective_worp` / WORP* blends historical + Sleeper projection — key dynasty_rating input
- `bookend_plan.picks_before_current_bookend` — sim of every pick BEFORE their current bookend (the gap while they wait)
- `current_bookend.planned_picks` — dynasty-first pair projection for their picks NOW (align with or refine this)
- `bookend_plan.between_bookends` — simulated league picks after current bookend until next bookend
- `next_bookend.planned_picks` — dynasty-first projected pair at the following bookend
- `next_bookend.targets_at_bookend` — dynasty-ranked best available if plans change
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
- `league_rankings.by_starter_ppg`: sum of starter HPPG/expected PPG — weekly scoring power from optimal lineup
- `league_rankings.by_trade_value` / `by_win_now`: market TV and win-now standings
- `league_team_rosters`: every manager's picks — infer tendencies (QB early, RB heavy, etc.)
- `available_by_position`: top 12 available per position with `dynasty_rating` per player
- `recent_draft_picks`: last 24 picks with team names
- `scoring`: league scoring rules (PPR, superflex, TD bonuses)

Account for:
- Vet-only startup vs separate reversed rookie draft
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
            f"{row['name']} (Dyn {row.get('dynasty_rating', '?')})"
            for row in (nb.get("top_by_dynasty_rating") or [])[:4]
        )
        lines.append(f"Next bookend #{nb.get('pick_no')}: {top or '—'}")
    pivot = state.value_pivot_summary(limit=4)
    overrides = pivot.get("take_bpa_over_need") or []
    if overrides:
        names = ", ".join(
            f"{row['name']} (BPA #{row['bpa_rank']} vs need #{row['need_rank']})"
            for row in overrides[:4]
        )
        lines.append(f"VBD overrides: {names}")
    wait = pivot.get("wait_for_later") or []
    if wait:
        names = ", ".join(f"{row['name']} ({row.get('reason') or ''})" for row in wait[:3])
        lines.append(f"Wait for later: {names}")
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
    system: str | None = None,
    feature: str = "advisor_stream",
) -> Iterator[str]:
    client = anthropic.Anthropic(api_key=api_key.strip())
    with stream_message(
        client,
        feature=feature,
        model=model,
        max_tokens=max_tokens,
        system=system or _system_prompt(),
        messages=messages,
    ) as stream:
        yield from stream.text_stream


def _stream_moonshot(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int = 2500,
    system: str | None = None,
) -> Iterator[str]:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system or _system_prompt()}, *messages],
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
    system: str | None = None,
    feature: str = "advisor_stream",
) -> Iterator[str]:
    if not api_key.strip():
        raise ValueError("API key is required for the selected advisor.")

    if not messages or messages[-1]["role"] != "user":
        raise ValueError("Last message must be from the user.")

    if provider == "anthropic":
        yield from _stream_anthropic(
            api_key=api_key,
            model=model,
            messages=messages,
            system=system,
            feature=feature,
        )
        return
    if provider == "moonshot":
        yield from _stream_moonshot(
            api_key=api_key, model=model, messages=messages, system=system
        )
        return
    raise ValueError(f"Unsupported provider: {provider}")


INSEASON_ADVISOR_PROMPTS: list[dict[str, str]] = [
    {
        "id": "suggest_trade",
        "label": "Suggest Trades",
        "question": (
            "What trades make sense for my team right now? Rank the best packages "
            "with manager names, TV math, package quality, and fairness."
        ),
    },
    {
        "id": "trade_targets",
        "label": "Trade Targets",
        "question": (
            "Who should I target in trades this week? Find realistic buy-low and "
            "sell-high paths — name specific managers and players with OVR context."
        ),
    },
    {
        "id": "drop_candidates",
        "label": "Drop Candidates",
        "question": (
            "Which players on my bench are the best drop candidates right now? "
            "Compare roster depth vs top free agents. Prioritize dynasty OVR and "
            "roster construction — not just this week's points."
        ),
    },
    {
        "id": "rookie_pick_prep",
        "label": "Rookie Pick Prep",
        "question": (
            "Help me prep for the upcoming rookie draft in this league. Recommend "
            "positional priorities and archetypes to target with my picks based on "
            "my roster needs and competitive window."
        ),
    },
]


def inseason_prompt_by_id(prompt_id: str) -> dict[str, str] | None:
    for row in INSEASON_ADVISOR_PROMPTS:
        if row["id"] == prompt_id:
            return row
    return None


def _inseason_metric_definitions() -> dict[str, str]:
    return {
        "dynasty_rating": "50–99 OVR — league-relative dynasty value headline grade.",
        "dynasty_score": "Raw 0–1 composite before the display curve.",
        "trade_value": "Blended dynasty market capital (dynasty-daddy + KTC).",
        "hppg": "Healthy points per game (snap-filtered).",
        "worp_ppg": "WORP per game — weekly production over replacement.",
        "avg_dynasty_rating": "Team roster average OVR.",
        "starter_total_ppg": "Sum of optimal-starter HPPG/expected PPG.",
        "contender_tier": "elite / contender / fringe / rebuild from contender_index.",
        "trade_surplus": "Positions where my depth ranks top/bottom of league — trade leverage.",
        "trade_tag": "core | trade | null — lineup marginal value vs backups; only tagged players are sell chips.",
        "lineup_delta_ppg": "Marginal PPG vs next realistic backup at position (production-weighted).",
        "tv_vs_production_gap": "TV percentile minus production percentile — positive means sell-high vs market.",
        "effective_tv": "Package TV after depth discount + consolidation premium (see evaluate_trade).",
        "exposure_flag": "Portfolio tag: conviction, concentrated, risk across my leagues.",
        "hppg_expected": "True when HPPG is projected (rookie/no nflverse) — shown as e in UI.",
        "draft_pick_tv": "Future pick trade value on same scale as player TV; tier from original owner's dynasty rank.",
        "validate_trade": "Opt-in counterparty lens: accept_likelihood, blockers, suggested_tweak (after suggest_trades).",
    }


def _inseason_system_prompt() -> str:
    return """You are an expert dynasty fantasy football in-season advisor for Dynasty Blackbook.

You receive a **small base context** (league name, scoring, page_context, focused_team summary).
Pull detail on demand via tools — do not guess player grades or roster contents.

IN-SEASON PRIORITY:
1. **dynasty_rating (OVR 50–99)** — primary lens for roster value and trade fairness.
2. **trade_surplus + league_rankings** — depth to sell vs holes to fill; name counterparties.
3. **my_team + starter_needs** — lineup gaps and bench clutter (use get_team).
4. **free_agents** — waiver adds that move the dynasty needle.
5. **draft_picks** — valued future picks (early/mid/late tier + TV on get_team).
6. **rookie_draft** (when in context) — 2026 rookie board + projected player at each upcoming pick slot. Use for pick-for-pick trades: who lands at 1.01 vs 1.04/1.06 matters as much as pick TV.

TOOLS:
- get_team(roster_id) — roster, needs, surplus, draft picks
- get_player(player_id) — OVR, TV, HPPG, injury, outlook
- search_players(query, position?) — name search in league pool
- get_league_rankings() — dynasty / win-now / TV standings
- get_free_agents(position?, limit?) — top FA board
- evaluate_trade(give, receive) — raw + effective TV, consolidation-adjusted fairness (±5%)
- validate_trade(counterparty_roster_id, give, receive) — opt-in LLM check: would they accept?
- suggest_trades(target_roster_id?, swap_mode?, rank_by_validation?) — surplus/buy/sell packages; set rank_by_validation=true only if user wants accept-likelihood ranking (costs extra LLM calls)
- calculate(expression) — safe math for TV sums
- web_search(query) — recent NFL injury updates, roster moves, beat reports (web only when configured)

TOOL CHOICE:
- League stats, rosters, TV, trades → get_team, get_player, search_players, evaluate_trade, suggest_trades
- Waiver adds → get_free_agents
- Breaking injury/news, practice reports, signings, suspensions → web_search (then cross-check get_player injury fields)
- Do not web_search for dynasty grades or trade values — those come from league tools

TRADE SKILL:
- For trade questions, call suggest_trades and/or evaluate_trade before recommending.
- Call validate_trade only when the user asks whether a specific package would be accepted.
- validate_trade includes projected 2026 rookies at each traded pick slot when available.
- Show TV math (use calculate when summing). Name managers, not just roster ids.
- Trade perspective: `focused_roster_id` is the manager the user picked in the **From** dropdown (defaults to their team). Use that roster for `suggest_trades` surplus/hooks — not `my_team` when they differ.

Account for superflex/TE premium in scoring, injuries, win-now vs rebuild (contender_tier).

Required sections (adapt to the question):
- **Bottom line** — 2–3 sentence verdict
- **Top moves** — ranked actionable recommendations
- **Trade paths** — specific managers/players when relevant
- **Risks / watch-outs** — injury, aging cliffs

On follow-ups, stay concise. Format with clear headings. Keep under 700 words unless complex."""


def build_inseason_advisor_context(raw: dict[str, Any]) -> dict[str, Any]:
    """Minimal base context for tool-loop advisor (no full league dump)."""
    return {
        "mode": "in_season",
        "league_id": raw.get("league_id"),
        "league_name": raw.get("league_name"),
        "season": raw.get("season"),
        "scoring": raw.get("scoring"),
        "page_context": raw.get("page_context"),
        "focused_team": raw.get("focused_team"),
        "my_team": raw.get("my_team"),
        "metric_definitions": _inseason_metric_definitions(),
        "prompt_templates": INSEASON_ADVISOR_PROMPTS,
    }


def build_inseason_user_message(context: dict[str, Any], user_question: str) -> str:
    payload = json.dumps(context, indent=2, default=str)
    question = user_question.strip() or INSEASON_ADVISOR_PROMPTS[0]["question"]
    return f"""Base context (JSON):
{payload}

Question:
{question}"""


def _chunk_text(text: str, size: int = 48) -> Iterator[str]:
    for i in range(0, len(text), size):
        yield text[i : i + size]


def stream_inseason_advisor(
    context: dict[str, Any],
    api_key: str,
    *,
    user_question: str = "",
    model: str = DEFAULT_MODEL,
    messages: list[dict[str, str]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_handler: Any | None = None,
    max_tool_rounds: int = 4,
) -> Iterator[str]:
    """Stream in-season advisor reply with optional Anthropic tool-use loop."""
    row = advisor_model_by_id(model)
    advisor_context = build_inseason_advisor_context(context)
    system = _inseason_system_prompt()

    if tools and tool_handler and row["provider"] == "anthropic":
        yield from _stream_inseason_with_tools(
            api_key=api_key,
            model=row["model"],
            system=system,
            context=advisor_context,
            user_question=user_question,
            messages=messages,
            tools=tools,
            tool_handler=tool_handler,
            max_tool_rounds=max_tool_rounds,
        )
        return

    if messages:
        yield from stream_advisor_reply(
            api_key,
            provider=row["provider"],  # type: ignore[arg-type]
            model=row["model"],
            messages=messages,
            system=system,
        )
        return

    yield from stream_advisor_reply(
        api_key,
        provider=row["provider"],  # type: ignore[arg-type]
        model=row["model"],
        messages=[
            {
                "role": "user",
                "content": build_inseason_user_message(advisor_context, user_question),
            }
        ],
        system=system,
    )


def _stream_inseason_with_tools(
    *,
    api_key: str,
    model: str,
    system: str,
    context: dict[str, Any],
    user_question: str,
    messages: list[dict[str, str]] | None,
    tools: list[dict[str, Any]],
    tool_handler: Any,
    max_tool_rounds: int,
) -> Iterator[str]:
    """Run tool loop; stream final assistant text after tools complete."""
    client = anthropic.Anthropic(api_key=api_key.strip())
    thread: list[dict[str, Any]] = list(messages or [])
    if not thread:
        thread.append(
            {
                "role": "user",
                "content": build_inseason_user_message(context, user_question),
            }
        )
    elif not any(
        row.get("role") == "user" and "Base context (JSON):" in str(row.get("content", ""))
        for row in thread
    ):
        payload = json.dumps(context, indent=2, default=str)
        thread.insert(
            0,
            {
                "role": "user",
                "content": f"Base context (JSON):\n{payload}\n\n(Use tools for roster and trade detail.)",
            },
        )

    for round_idx in range(max_tool_rounds):
        if round_idx == 0:
            yield "⏳ Running league tools…\n\n"

        response = create_message(
            client,
            feature="advisor_tool_loop",
            model=model,
            max_tokens=2500,
            system=system,
            messages=thread,
            tools=tools,
            extra={"round": round_idx},
        )

        if response.stop_reason == "tool_use":
            thread.append({"role": "assistant", "content": response.content})
            tool_results: list[dict[str, Any]] = []
            tool_names = [
                block.name for block in response.content if block.type == "tool_use"
            ]
            if tool_names:
                yield f"_Calling {', '.join(tool_names)}…_\n\n"
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = tool_handler(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    }
                )
            thread.append({"role": "user", "content": tool_results})
            continue

        text_parts = [
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ]
        final_text = "".join(text_parts)
        yield from _chunk_text(final_text)
        return

    yield "Advisor hit the tool-round limit — try a narrower question."


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
