from __future__ import annotations

from typing import Any

from dynasty_draft.adp import AdpIndex
from dynasty_draft.pick_values import _simulate_through
from dynasty_draft.recommender import DraftState
from dynasty_draft.worp_projection import WorpProjector


def _score_pool_at_pick(
    state: DraftState,
    pool: list[tuple[str, Any]],
    pick_no: int,
    *,
    worp_projector: WorpProjector,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Rank simulated remaining pool the way the user would at a future pick."""
    adp = AdpIndex(state.war)
    round_no = (pick_no - 1) // state._teams() + 1
    fake_available = list(pool)
    if not fake_available:
        return []

    trade_vals = [p.trade_value for _, p in fake_available]
    max_tv = max(trade_vals) if trade_vals else 1.0
    needs = state.starter_needs()
    adjustments = state._position_adjustments(round_no)
    need_weights: dict[str, float] = adjustments["need_weights"]
    penalties: dict[str, float] = adjustments["penalties"]

    dynasty_by_id = state.dynasty_scores(fake_available)
    scored: list[dict[str, Any]] = []
    for player_id, player in fake_available:
        years_exp = state.sleeper_players.get(player_id, {}).get("years_exp")
        years_exp_int = int(years_exp) if years_exp is not None else None
        eff_worp, worp_proj = worp_projector.effective_worp(player, years_exp=years_exp_int)
        tv_norm = player.trade_value / max_tv if max_tv else 0.0
        worp_norm = (max(eff_worp or 0, 0) / 1.5) if eff_worp is not None else tv_norm * 0.85
        base = state.trade_weight * tv_norm + state.worp_weight * min(worp_norm, 1.0)
        need_boost = needs.get(player.pos, 0) * need_weights.get(player.pos, 0.05)
        penalty = penalties.get(player.pos, 0.0)
        final = base + need_boost - penalty
        adp_pick = adp.pick_no(player.name)
        adp_delta = adp.delta(player.name, pick_no) if adp_pick else None
        dynasty = dynasty_by_id.get(player_id) or {}
        scored.append(
            {
                "name": player.name,
                "pos": player.pos,
                "trade_value": player.trade_value,
                "worp": player.worp,
                "projected_worp": eff_worp if worp_proj else None,
                "dynasty_rating": dynasty.get("dynasty_rating"),
                "adp_pick": adp_pick,
                "adp_delta": adp_delta,
                "score": final,
                "likely_faller": adp_pick is not None and adp_pick < pick_no - 1,
                "value_at_slot": adp_delta is not None and adp_delta >= 4,
            }
        )
    scored.sort(key=lambda row: row["score"], reverse=True)
    return scored[:limit]


def build_fall_analysis(state: DraftState) -> dict[str, Any]:
    """
    Who could realistically still be on the board at each of your upcoming bookend picks,
    based on ADP + needs simulation (not just current-board WORP leaders).
    """
    info = state.next_pick_info()
    bookend = info.get("consecutive_picks") or []
    if not bookend:
        pick_no = info.get("pick_no")
        if pick_no:
            bookend = [pick_no]

    worp_projector = WorpProjector(state.war)
    picks_analysis: list[dict[str, Any]] = []

    for pick_no in bookend:
        if pick_no is None:
            continue
        pool = _simulate_through(state, pick_no)
        ranked = _score_pool_at_pick(state, pool, pick_no, worp_projector=worp_projector)
        fallers = [row for row in ranked if row.get("likely_faller")]
        values = [row for row in ranked if row.get("value_at_slot")]
        picks_analysis.append(
            {
                "pick_no": pick_no,
                "round": (pick_no - 1) // state._teams() + 1,
                "top_available_sim": ranked[:12],
                "likely_fallers": fallers[:8],
                "value_vs_adp": values[:8],
                "consensus_top_adp_still_available": [
                    row
                    for row in sorted(
                        [
                            {
                                "name": p.name,
                                "pos": p.pos,
                                "trade_value": p.trade_value,
                                "adp_pick": AdpIndex(state.war).pick_no(p.name),
                            }
                            for _, p in pool
                        ],
                        key=lambda row: row["adp_pick"] or 9999,
                    )
                    if row["adp_pick"] is not None
                ][:10],
            }
        )

    next_bookend = state.consecutive_pick_numbers(
        from_pick=(bookend[-1] + 1) if bookend else None
    )
    next_analysis: list[dict[str, Any]] = []
    for pick_no in next_bookend[:2]:
        pool = _simulate_through(state, pick_no)
        ranked = _score_pool_at_pick(state, pool, pick_no, worp_projector=worp_projector)
        next_analysis.append(
            {
                "pick_no": pick_no,
                "top_available_sim": ranked[:10],
                "likely_fallers": [row for row in ranked if row.get("likely_faller")][:6],
            }
        )

    return {
        "current_bookend_picks": bookend,
        "at_each_pick": picks_analysis,
        "next_bookend": next_analysis,
        "note": (
            "Use likely_fallers and top_available_sim — not just current-board WORP leaders. "
            "Players with negative historical WORP may have projected_worp for sophomores."
        ),
    }
