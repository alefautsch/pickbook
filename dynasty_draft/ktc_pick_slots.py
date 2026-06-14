"""Expand KTC tier picks (Early/Mid/Late) into slot-specific values (2026 Pick 1.03).

Mirrors KeepTradeCut trade-calculator logic:
- Future years: calcPicksSimple (tier interpolation)
- Current rookie draft year: rookie-class anchoring at the top of round 1
"""

from __future__ import annotations

import re
from typing import Any

from dynasty_draft.inseason_pick_values import SlotTier

_MAX_PLAYER_VAL = 9999
_TIER_ORDER: dict[str, int] = {"early": 0, "mid": 1, "late": 2}
_PICK_TIER_RE = re.compile(
    r"^(?P<season>\d{4})\s+(?P<tier>Early|Mid|Late)\s+(?P<round>\d+)(?:st|nd|rd|th)$",
    re.I,
)


def parse_tier_pick_name(name: str) -> tuple[str, int, SlotTier] | None:
    match = _PICK_TIER_RE.match(name.strip())
    if match is None:
        return None
    return (match.group("season"), int(match.group("round")), match.group("tier").lower())  # type: ignore[return-value]


def tier_values_for_season(
    rows: list[dict[str, Any]],
    season: str | int,
    *,
    superflex: bool = True,
) -> list[float]:
    """Ordered tier anchor values for one draft season (12 tiers = 4 rounds × 3 bands)."""
    keyed: list[tuple[int, int, float]] = []
    for row in rows:
        parsed = parse_tier_pick_name(str(row.get("name") or ""))
        if parsed is None or parsed[0] != str(season):
            continue
        _, round_no, tier = parsed
        keyed.append((round_no, _TIER_ORDER[tier], float(row["value"])))
    keyed.sort()
    return [value for _, _, value in keyed]


def _calc_simple_single_mode(tier_values: list[float]) -> list[float]:
    """Port of KTC calcPicksSimpleSingleMode (superflex/1QB value list only)."""
    if len(tier_values) < 2:
        return list(tier_values)

    out: list[float] = []
    for seg_idx in range(len(tier_values) - 1):
        high = tier_values[seg_idx]
        low = tier_values[seg_idx + 1]
        step = (high - low) / 8.0

        if seg_idx == 0:
            out.append(min(_MAX_PLAYER_VAL - 1, high + round(7 * step)))
            out.append(min(_MAX_PLAYER_VAL - 1, high + round(3 * step)))

        pick_step = 1
        while pick_step < 8:
            out.append(high - round(pick_step * step))
            pick_step += 2

        if seg_idx == len(tier_values) - 2:
            out.append(max(0, low - round(step)))
            out.append(max(0, low - round(3 * step)))

    return out


def _calc_rookie_single_mode(
    tier_values: list[float],
    rookie_values: list[float],
) -> list[float]:
    """Anchor 1.01/1.02 to the rookie class; keep KTC tier interpolation for 1.03+."""
    simple = _calc_simple_single_mode(tier_values)
    if not simple or not rookie_values:
        return simple

    rookies = sorted((float(v) for v in rookie_values), reverse=True)
    top = rookies[0]
    second = rookies[1] if len(rookies) > 1 else top * 0.85
    early = tier_values[0]
    step = (tier_values[0] - tier_values[1]) / 8.0 if len(tier_values) > 1 else 0.0

    out = list(simple)
    if early < top:
        out[0] = min(_MAX_PLAYER_VAL - 1, top * 1.03)
        if early + round(step) < second:
            out[1] = min(_MAX_PLAYER_VAL - 5, second * 1.02)
        else:
            out[1] = min(_MAX_PLAYER_VAL - 1, early + round(step))
        if out[1] > out[0]:
            out[1] = out[0] * 0.92
    return out


def expand_slot_values(
    tier_values: list[float],
    *,
    season: str | int,
    league_size: int = 12,
    rounds: int = 4,
    rookie_values: list[float] | None = None,
    use_rookie_mode: bool = False,
) -> dict[tuple[int, int], float]:
    """Map (round, slot_in_round) → TV for one season."""
    if not tier_values:
        return {}

    if use_rookie_mode and rookie_values:
        flat = _calc_rookie_single_mode(tier_values, rookie_values)
    else:
        flat = _calc_simple_single_mode(tier_values)

    slots: dict[tuple[int, int], float] = {}
    idx = 0
    for round_no in range(1, rounds + 1):
        for slot_in_round in range(1, league_size + 1):
            if idx < len(flat):
                slots[(round_no, slot_in_round)] = round(float(flat[idx]), 1)
            idx += 1
    return slots


def rookie_prospect_values(
    war_players: list[Any],
    *,
    ktc_lookup: Any | None = None,
    min_tv: float = 1000.0,
) -> list[float]:
    """Prospects without WORP tier (college / undrafted) sorted by blended TV."""
    values: list[float] = []
    for player in war_players:
        worp_tier = getattr(player, "worp_tier", None)
        if worp_tier is not None:
            continue
        tv = float(getattr(player, "trade_value", 0) or 0)
        if tv < min_tv:
            continue
        name = getattr(player, "name", "")
        if ktc_lookup is not None and name:
            ktc_tv = ktc_lookup(name)
            if ktc_tv is not None:
                tv = (tv + float(ktc_tv)) / 2.0
        values.append(tv)
    values.sort(reverse=True)
    return values
