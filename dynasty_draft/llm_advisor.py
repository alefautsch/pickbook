from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import anthropic

from dynasty_draft.draft_context import build_league_team_rosters, build_scoring_context
from dynasty_draft.pick_projector import project_next_picks
from dynasty_draft.recommender import DraftState

DEFAULT_MODEL = "claude-sonnet-4-6"
RECENT_PICKS_LIMIT = 24
AVAILABLE_PER_POSITION = 12


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
                "trade_value": war.trade_value if war else None,
                "worp": war.worp if war else None,
            }
        )
    return rows


def _bookend_plan_summary(state: DraftState) -> dict[str, Any]:
    proj = project_next_picks(state)
    current = proj.get("current_bookend") or {}
    nxt = proj.get("next_bookend") or {}
    between = proj.get("between_bookends") or {}
    return {
        "current_bookend_picks": current.get("pick_numbers") or [],
        "current_planned_pair": current.get("planned_picks") or [],
        "next_bookend_picks": nxt.get("pick_numbers") or [],
        "next_planned_pair": nxt.get("planned_picks") or [],
        "targets_at_next_bookend": nxt.get("targets_at_bookend") or [],
        "likely_gone_before_next_bookend": between.get("likely_off_board") or [],
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
        "strategy_notes": state.strategy.strategy_notes(state.war),
        "reserved_rookies": state.strategy.reserved_players(state.war),
        "my_roster": state.roster_summary(),
        "starter_needs": state.starter_needs(),
        "league_team_rosters": build_league_team_rosters(state),
        "available_by_position": state.recommend_by_position(per_pos=per_position),
        "pick_projection": project_next_picks(state),
        "bookend_plan": _bookend_plan_summary(state),
        "tier_cliffs": state.tier_cliffs(),
        "recent_draft_picks": _recent_picks(state),
        "trade_weight": state.trade_weight,
        "worp_weight": state.worp_weight,
        "league_name": league.get("name"),
    }


def _system_prompt() -> str:
    return """You are an expert dynasty fantasy football draft advisor.

Your user weights trade value 65% and WORP (win-now) 35%.
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

Use `pick_projection` and `bookend_plan`:
- `current_bookend.planned_picks` — projection assumes they take this pair NOW (align with or refine this)
- `between_bookends` — simulated league picks between current and next bookend
- `next_bookend.planned_picks` — projected pair at the following bookend
- `next_bookend.targets_at_bookend` — best available if plans change
- `bookend_plan.likely_gone_before_next_bookend` — do NOT tell them to wait on these

ADP proxy = trade value, adjusted per team positional needs.

Use the full league context:
- `league_team_rosters`: every manager's picks — infer tendencies (QB early, RB heavy, etc.)
- `available_by_position`: top 12 available per position right now
- `recent_draft_picks`: last 24 picks with team names
- `scoring`: league scoring rules (PPR, superflex, TD bonuses)

Account for:
- Vet-only startup vs separate reversed rookie draft
- Reserved rookies (already penciled in — don't recommend vet RB early if Love is reserved)
- Superflex / 2QB leagues (QB premium is real)
- Tier cliffs in the data

Format with clear headings. Keep under 800 words unless the decision is complex."""


def _user_prompt(context: dict[str, Any], user_question: str) -> str:
    payload = json.dumps(context, indent=2, default=str)
    question = user_question.strip() or (
        "I'm at the bookend with two picks in a row. What should I take with each pick "
        "and what pairings maximize trade value + winning?"
    )
    return f"""Draft context (JSON):
{payload}

Question:
{question}"""


def stream_evaluate_picks(
    state: DraftState,
    api_key: str,
    *,
    user_question: str = "",
    model: str = DEFAULT_MODEL,
    per_position: int = AVAILABLE_PER_POSITION,
) -> Iterator[str]:
    if not api_key.strip():
        raise ValueError("Anthropic API key is required.")

    context = build_advisor_context(state, per_position=per_position)
    client = anthropic.Anthropic(api_key=api_key.strip())
    with client.messages.stream(
        model=model,
        max_tokens=2500,
        system=_system_prompt(),
        messages=[
            {
                "role": "user",
                "content": _user_prompt(context, user_question),
            }
        ],
    ) as stream:
        yield from stream.text_stream


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
