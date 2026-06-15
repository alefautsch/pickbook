"""Counterparty-perspective trade validation via a focused LLM call."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

import anthropic

from backend.config import get_settings
from backend.services.llm_usage import DEFAULT_VALIDATION_MODEL, create_message

AcceptLikelihood = Literal["low", "medium", "high"]
FairnessView = Literal["favors_them", "fair", "favors_you"]

ACCEPT_LIKELIHOOD_SCORE: dict[str, float] = {
    "low": 0.0,
    "medium": 0.55,
    "high": 1.0,
}


def validation_accept_score(validation: dict[str, Any]) -> float | None:
    """Scalar for ranking packages by counterparty accept likelihood."""
    if validation.get("skipped") or validation.get("error"):
        return None
    likelihood = str(validation.get("accept_likelihood") or "medium").lower()
    score = ACCEPT_LIKELIHOOD_SCORE.get(likelihood, 0.55)
    if validation.get("would_improve_their_roster"):
        score += 0.12
    fairness = str(validation.get("fairness_from_counterparty_view") or "fair").lower()
    if fairness == "favors_them":
        score += 0.05
    elif fairness == "favors_you":
        score -= 0.08
    return round(min(1.0, max(0.0, score)), 3)


_VALIDATION_SYSTEM = """You are a dynasty fantasy football trade analyst.
Your ONLY job: decide whether review_for_team would ACCEPT this trade if the_other_team offered it.

You receive:
- review_for_team: the manager you are advising (roster, needs, surplus, contender window)
- the_other_team: the other manager in the deal
- review_for_team_trade: what review_for_team gives up vs what they get back
- Per-asset depth context (lineup_delta_ppg = marginal PPG lost if that player is moved)
- Post-trade ideal starter lineup impact keyed by team name (starter_ppg_before/after/delta)
- review_for_team_tv: TV math from review_for_team's perspective ONLY — use this for fairness
- rookie_draft_context (when present): 2026 rookie board + projected player at each traded pick slot

Rules:
- Judge ONLY from review_for_team's interests. Ignore any other manager's wants.
- Never reference a logged-in user, "my team", is_me, or who is using the app.
- In reasoning and blockers, use team_name fields only — never say "you", "they", "proposer", or "counterparty".
- review_for_team_tv.net_tv_delta positive = review_for_team receives MORE total TV (favors review_for_team).
- review_for_team_tv.net_tv_delta negative = review_for_team receives LESS total TV (favors the_other_team).
- fairness_from_counterparty_view: favors_them = favors review_for_team; favors_you = favors the_other_team.
- Only cite players and picks explicitly listed in the trade payload.
- Rebuilders hoard early picks; contenders ship surplus picks/depth for win-now production.
- A trade can be TV-lopsided but still accepted when it fixes a critical need from surplus depth.
- For contenders, weigh starter_ppg_delta heavily: a large positive delta at a need position can justify TV overpay.
- For rebuilders, negative starter_ppg_delta is acceptable when acquiring youth/picks; positive delta is a bonus.
- If review_for_team's lineup impact shows new incoming starters or materially higher starter PPG, that supports acceptance.
- When rookie_draft_context is present, weigh projected rookies at traded pick slots — a manager may overpay TV to move up for a specific prospect (e.g. 1.01 for an elite RB) or accept less when the picks they give up project to weaker fits.
- REQUIRED when rookie_draft_context.picks_in_trade is non-empty: reasoning MUST cite pick labels and likely_range prospects (e.g. "2026 1.01 is Jeremiyah Love; 1.04 may land Makai Lemon or Kenyon Sadiq").
- Use picks_in_trade.likely_range / projected_rookie and fills_need_for_acquirer; in TEP leagues (te_premium > 0), TE prospects at mid-first slots matter more.
- Be specific: name players, positions, pick slots, PPG deltas, roster holes, and projected rookies when relevant.
- tradable_inventory lists exact player names and pick labels each team owns — use ONLY those in counter_offer.
- When accept_likelihood is low or medium, propose counter_offer: a revised package from the_other_team's perspective (what they give / receive) that review_for_team is more likely to accept. Keep the same core acquisition goal when possible (e.g. same target pick/player in proposer_receives).
- counter_offer must use exact player names and pick labels from tradable_inventory. null when accept_likelihood is high.

Respond with ONLY valid JSON (no markdown):
{
  "accept_likelihood": "low" | "medium" | "high",
  "fairness_from_counterparty_view": "favors_them" | "fair" | "favors_you",
  "would_improve_their_roster": true | false,
  "reasoning": "2-4 sentences about review_for_team by name",
  "blockers": ["short bullet", "..."],
  "suggested_tweak": "one concrete adjustment or null",
  "counter_offer": null | {
    "proposer_gives": { "players": ["Name"], "picks": ["2026 1.10"] },
    "proposer_receives": { "players": ["Name"], "picks": ["2026 1.01"] },
    "rationale": "why review_for_team accepts this revision"
  }
}
"""


_FIX_SYSTEM = """You are a dynasty fantasy football trade mediator.
Both managers have already been graded on whether they would accept the current offer.

You receive:
- side_a_team / side_b_team: names and roster context
- trade_package: what each side gives and receives (players + picks with TV)
- tv_evaluation: fairness math for the package
- rookie_draft_context (when present): projected rookie at each 2026 pick slot
- side_a_validation / side_b_validation: accept likelihood, reasoning, blockers, tweaks

Your job: propose ONE concrete fix so BOTH sides are more likely to accept.
- Use each side's blockers and suggested_tweak as hints.
- When picks are involved, reference projected rookies at those slots.
- Prefer minimal changes (small pick swap, add a depth piece, shave TV on one side).
- trade_package: the CURRENT deal — each team's exact gives and receives. Never swap which team gives which asset.
- picks_given_in_trade: pick labels each team is already giving in trade_package (only those teams may substitute those picks).
- pick_downgrade_options: per team giving a pick — owned picks with LOWER TV than what they currently give. Empty list means no first-round (or pick) downgrade exists in inventory; remove the pick from their offer or have the other side add assets instead.
- tv_by_side: each team's gives/receives adjusted TV and net (negative net_adjusted_tv = that team overpays).
- pick_tv_catalog: exact TV for every owned pick label.
- Pick TV direction: earlier slot = higher TV (2026 1.04 > 2026 1.06 > 2026 1.08 in the same round).
- If a team overpays (net_adjusted_tv negative), they give MORE adjusted TV than they receive.
  To reduce their overpay, remove assets from THEIR give package or substitute a LATER pick (higher round.decimal, LOWER TV) THEY are giving.
  Replacing 1.06 with 1.04 in a give package INCREASES TV — that is wrong when trimming overpay.
  Never claim a swap "reduces bleed/overpay" when the substitute pick has higher TV than the one removed.
  Never move a traded pick to the other team's give package — e.g. if Team A gives 2026 1.06, only Team A can swap that pick.
  If pick_downgrade_options[team] is empty, do NOT invent a later first — either remove the pick from that team's give package or add value from the other side.
- CRITICAL: tradable_inventory lists every pick label and player each team actually owns.
  Only assign a pick or player to a team if it appears in that team's tradable_inventory.
  Never invent picks (e.g. do not add a 2026 2.05 or 2027 1st unless that exact label is listed).
  Pick substitutions ("instead of") must replace a pick that SAME team is already giving in trade_package.
  New sweeteners use "adds" and must still be in that team's tradable_inventory.
- Name specific players and pick labels from the payload only.
- Use team names — never "you" or "they".

Respond with ONLY valid JSON (no markdown):
{
  "headline": "short title for the fix",
  "reasoning": "2-4 sentences explaining why this works for both teams",
  "adjustments": ["concrete change 1", "concrete change 2"],
  "both_sides_likely_accept": true | false
}
"""


_PICK_LABEL_IN_TEXT_RE = re.compile(r"20\d{2}\s+(?:\d+\.\d{2}|\d+(?:st|nd|rd|th))", re.I)
_RE_SWAP_PICKS_RE = re.compile(
    r"swapp?(?:ing|ed)?\s+(?:the\s+)?(?P<out_pick>20\d{2}\s+(?:\d+\.\d{2}|\d+(?:st|nd|rd|th)))"
    r".*?\bfor\b.*?"
    r"(?P<in_pick>20\d{2}\s+(?:\d+\.\d{2}|\d+(?:st|nd|rd|th)))",
    re.I,
)
_RE_REDUCE_OVERPAY_CLAIM_RE = re.compile(
    r"reduc(?:e|es|ing)|lessen|lower(?:s|ing)?\s+(?:the\s+)?(?:immediate\s+)?(?:tv\s+)?(?:bleed|overpay)|clos(?:e|es|ing)\s+(?:the\s+)?tv\s+gap|trim(?:s|ming)?\s+capital",
    re.I,
)
_INSTEAD_OF_PICK_RE = re.compile(
    r"instead of\s+(?P<old_pick>20\d{2}\s+(?:\d+\.\d{2}|\d+(?:st|nd|rd|th)))",
    re.I,
)
_INSTEAD_OF_SUB_RE = re.compile(
    r"(?P<new_pick>20\d{2}\s+(?:\d+\.\d{2}|\d+(?:st|nd|rd|th)))"
    r"\s*\(instead of\s+(?P<old_pick>20\d{2}\s+(?:\d+\.\d{2}|\d+(?:st|nd|rd|th)))\)",
    re.I,
)


def _normalize_pick_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip())


def _pick_tv_catalog(*inventories: dict[str, Any]) -> dict[str, float]:
    catalog: dict[str, float] = {}
    for inventory in inventories:
        for pick in inventory.get("draft_picks") or []:
            label = _normalize_pick_label(str(pick.get("label") or ""))
            tv = pick.get("tv")
            if label and tv is not None:
                catalog[label] = float(tv)
    return catalog


def _team_tv_summary(*, gives_adj: float, receives_adj: float) -> dict[str, Any]:
    net = receives_adj - gives_adj
    return {
        "gives_adjusted_tv": round(gives_adj, 2),
        "receives_adjusted_tv": round(receives_adj, 2),
        "net_adjusted_tv": round(net, 2),
        "overpays": net < -0.5,
        "overpay_tv": round(abs(net), 2) if net < 0 else 0.0,
    }


def _lookup_pick_tv(label: str, catalog: dict[str, float]) -> float | None:
    key = _normalize_pick_label(label)
    if key in catalog:
        return catalog[key]
    lowered = key.lower()
    for catalog_label, tv in catalog.items():
        if catalog_label.lower() == lowered:
            return tv
    return None


def _give_pick_upgrade_substitution(text: str, tv_catalog: dict[str, float]) -> str | None:
    """Give-package swap replaced a pick with an earlier/higher-TV pick."""
    for match in _INSTEAD_OF_SUB_RE.finditer(text):
        new_pick = _normalize_pick_label(match.group("new_pick"))
        old_pick = _normalize_pick_label(match.group("old_pick"))
        tv_new = _lookup_pick_tv(new_pick, tv_catalog)
        tv_old = _lookup_pick_tv(old_pick, tv_catalog)
        if tv_new is None or tv_old is None:
            continue
        if tv_new > tv_old + 25:
            delta = tv_new - tv_old
            return (
                f"Substituting {new_pick} ({tv_new:,.0f} TV) for {old_pick} ({tv_old:,.0f} TV) "
                f"in the give package adds ~{delta:,.0f} TV — use a later/weaker pick to reduce overpay."
            )
    return None


def _inverted_pick_swap_claim(text: str, tv_catalog: dict[str, float]) -> str | None:
    """Detect 'swap low pick for high pick reduces overpay' — direction is backwards."""
    upgrade = _give_pick_upgrade_substitution(text, tv_catalog)
    if upgrade and _RE_REDUCE_OVERPAY_CLAIM_RE.search(text):
        return upgrade

    if not _RE_REDUCE_OVERPAY_CLAIM_RE.search(text):
        return None
    match = _RE_SWAP_PICKS_RE.search(text)
    if match is None:
        return upgrade
    out_pick = _normalize_pick_label(match.group("out_pick"))
    in_pick = _normalize_pick_label(match.group("in_pick"))
    tv_out = _lookup_pick_tv(out_pick, tv_catalog)
    tv_in = _lookup_pick_tv(in_pick, tv_catalog)
    if tv_out is None or tv_in is None:
        return upgrade
    if tv_in <= tv_out + 25:
        return upgrade
    delta = tv_in - tv_out
    swap_warning = (
        f"Swapping {out_pick} ({tv_out:,.0f} TV) for {in_pick} ({tv_in:,.0f} TV) in the give "
        f"package adds ~{delta:,.0f} TV to the overpaying side — it does not reduce bleed."
    )
    return swap_warning


def _pick_downgrade_options(
    *,
    trade_package: dict[str, Any],
    tradable_inventory: dict[str, dict[str, Any]],
    pick_tv_catalog: dict[str, float],
) -> dict[str, list[dict[str, Any]]]:
    """Owned picks a team could substitute in their give package to reduce TV."""
    options: dict[str, list[dict[str, Any]]] = {}
    for team_name, sides in trade_package.items():
        give_picks = (sides.get("gives") or {}).get("picks") or []
        if not give_picks:
            options[team_name] = []
            continue
        current_tvs = [
            _lookup_pick_tv(_normalize_pick_label(str(p.get("label") or "")), pick_tv_catalog)
            for p in give_picks
        ]
        current_tvs = [tv for tv in current_tvs if tv is not None]
        if not current_tvs:
            options[team_name] = []
            continue
        floor_tv = min(current_tvs)
        owned_labels = tradable_inventory.get(team_name, {}).get("pick_labels") or []
        giving_labels = {
            _normalize_pick_label(str(p.get("label") or ""))
            for p in give_picks
            if str(p.get("label") or "").strip()
        }
        team_options: list[dict[str, Any]] = []
        for label in owned_labels:
            norm = _normalize_pick_label(label)
            if norm in giving_labels:
                continue
            tv = _lookup_pick_tv(norm, pick_tv_catalog)
            if tv is not None and tv < floor_tv - 25:
                team_options.append({"label": norm, "tv": round(tv, 2)})
        team_options.sort(key=lambda row: -row["tv"])
        options[team_name] = team_options
    return options


def _trade_give_pick_labels(trade_package: dict[str, Any]) -> dict[str, set[str]]:
    """Pick labels each team gives in the current trade_package."""
    result: dict[str, set[str]] = {}
    for team_name, sides in trade_package.items():
        picks = (sides.get("gives") or {}).get("picks") or []
        labels = {
            _normalize_pick_label(str(pick.get("label") or ""))
            for pick in picks
            if str(pick.get("label") or "").strip()
        }
        result[str(team_name)] = labels
    return result


def _pick_giver_in_trade(trade_give_picks: dict[str, set[str]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for team, picks in trade_give_picks.items():
        for label in picks:
            mapping[label] = team
    return mapping


def _give_clause_slice(text: str, *, team_start: int, team_len: int) -> str:
    """Portion of text after a team name that describes what they give (before 'receives')."""
    window = text[team_start : min(len(text), team_start + team_len + 140)]
    receives_match = re.search(r"\breceives?\b", window, re.I)
    if receives_match:
        return window[: receives_match.start()]
    return window


def _wrong_team_pick_violations(
    text: str,
    *,
    trade_give_picks: dict[str, set[str]],
    team_names: list[str],
) -> list[str]:
    """Detect fix text that assigns a traded pick to the wrong team's give package."""
    if not trade_give_picks:
        return []

    pick_giver = _pick_giver_in_trade(trade_give_picks)
    if not pick_giver:
        return []

    violations: list[str] = []
    lowered = text.lower()
    givers = _teams_attributed_as_giver(text, team_names)

    for giver in givers:
        marker = giver.lower()
        idx = lowered.find(marker)
        if idx < 0:
            continue
        window = _give_clause_slice(text, team_start=idx, team_len=len(marker))
        window_lower = window.lower()
        is_add = bool(re.search(r"\badds?\b", window_lower))

        for match in _INSTEAD_OF_PICK_RE.finditer(text):
            if abs(match.start() - idx) > 160:
                continue
            if match.start() > idx and "receives" in text[idx:match.start()].lower():
                continue
            old_pick = _normalize_pick_label(match.group("old_pick"))
            owned_gives = trade_give_picks.get(giver, set())
            if old_pick and old_pick not in owned_gives:
                actual = pick_giver.get(old_pick)
                if actual:
                    violations.append(
                        f"{old_pick} is given by {actual} in the current trade, not {giver}"
                    )
                else:
                    violations.append(
                        f"{giver} does not give {old_pick} in the current trade"
                    )

        if is_add:
            continue

        for label in _pick_labels_in_text(window):
            norm = _normalize_pick_label(label)
            actual_giver = pick_giver.get(norm)
            if actual_giver and actual_giver != giver:
                violations.append(
                    f"{norm} is given by {actual_giver} in the current trade, not {giver}"
                )

    # Reasoning often swaps picks without "Team gives" — flag team + pick co-mentioned wrongly.
    if not (re.search(r"\bgives?\b", text, re.I) and re.search(r"\breceives?\b", text, re.I)):
        for label in _pick_labels_in_text(text):
            norm = _normalize_pick_label(label)
            actual_giver = pick_giver.get(norm)
            if not actual_giver:
                continue
            for match in _PICK_LABEL_IN_TEXT_RE.finditer(text):
                if _normalize_pick_label(match.group(0)) != norm:
                    continue
                pick_pos = match.start()
                for team in team_names:
                    team_pos = lowered.find(team.lower())
                    if team_pos < 0 or abs(team_pos - pick_pos) > 100:
                        continue
                    if team != actual_giver:
                        violations.append(
                            f"{norm} is given by {actual_giver} in the current trade, not {team}"
                        )

    return list(dict.fromkeys(violations))


def _tradable_inventory(team: dict[str, Any]) -> dict[str, Any]:
    picks = [_compact_pick(pick) for pick in (team.get("draft_picks") or [])]
    pick_labels = sorted(
        {
            str(pick.get("label") or "").strip()
            for pick in picks
            if str(pick.get("label") or "").strip()
        }
    )
    player_names: set[str] = set()
    players_by_name: dict[str, dict[str, Any]] = {}
    for row in team.get("players") or []:
        name = str(row.get("name") or row.get("player_name") or "").strip()
        if name:
            player_names.add(name)
            players_by_name[name.lower()] = row
    for row in team.get("trade_candidates") or []:
        name = str(row.get("name") or row.get("player_name") or "").strip()
        if name:
            player_names.add(name)
            players_by_name.setdefault(name.lower(), row)
    return {
        "draft_picks": picks,
        "pick_labels": pick_labels,
        "player_names": sorted(player_names),
        "players_by_name": players_by_name,
    }


def _pick_labels_in_text(text: str) -> set[str]:
    return {match.group(0).strip() for match in _PICK_LABEL_IN_TEXT_RE.finditer(text)}


def _teams_attributed_as_giver(text: str, team_names: list[str]) -> list[str]:
    lowered = text.lower()
    givers: list[str] = []
    for name in team_names:
        marker = name.lower()
        idx = lowered.find(marker)
        if idx < 0:
            continue
        after = lowered[idx + len(marker) : idx + len(marker) + 48]
        if re.search(r"\b(gives?|adds?|sends?|includes?)\b", after):
            givers.append(name)
    return givers


def _invalid_pick_assignments(
    text: str,
    *,
    team_names: dict[str, dict[str, Any]],
) -> list[str]:
    """Pick labels a team is asked to give but does not own."""
    violations: list[str] = []
    labels = _pick_labels_in_text(text)
    if not labels:
        return violations

    names = list(team_names.keys())
    givers = _teams_attributed_as_giver(text, names)
    if not givers:
        return violations

    for giver in givers:
        owned = set(team_names[giver].get("pick_labels") or [])
        for label in labels:
            if label not in owned:
                violations.append(f"{giver} does not own {label}")
    return violations


def _sanitize_fix_against_inventory(
    fix: dict[str, Any],
    *,
    tradable_inventory: dict[str, dict[str, Any]],
    trade_package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Drop adjustments that reference picks a team does not own or wrong team's give package."""
    if not tradable_inventory:
        return fix

    trade_give_picks = _trade_give_pick_labels(trade_package or {})
    team_names = list(tradable_inventory.keys())

    valid_adjustments: list[str] = []
    dropped: list[str] = []
    for adjustment in fix.get("adjustments") or []:
        violations = _invalid_pick_assignments(adjustment, team_names=tradable_inventory)
        violations.extend(
            _wrong_team_pick_violations(
                adjustment,
                trade_give_picks=trade_give_picks,
                team_names=team_names,
            )
        )
        if violations:
            dropped.append(adjustment)
            continue
        valid_adjustments.append(adjustment)

    reasoning = str(fix.get("reasoning") or "")
    reasoning_violations = _invalid_pick_assignments(reasoning, team_names=tradable_inventory)
    reasoning_violations.extend(
        _wrong_team_pick_violations(
            reasoning,
            trade_give_picks=trade_give_picks,
            team_names=team_names,
        )
    )

    result = dict(fix)
    result["adjustments"] = valid_adjustments

    if dropped or reasoning_violations:
        result["both_sides_likely_accept"] = False
        notes: list[str] = []
        if dropped:
            notes.append(
                "Removed invalid trade-role suggestions: " + "; ".join(dropped[:2])
            )
        if reasoning_violations:
            notes.append(
                "Reasoning referenced unavailable or misassigned picks: "
                + "; ".join(sorted(set(reasoning_violations))[:3])
            )
        warning = " ".join(notes)
        if reasoning:
            result["reasoning"] = f"{reasoning} ({warning})"
        else:
            result["reasoning"] = warning
        if not valid_adjustments and not result.get("headline"):
            result["headline"] = "No valid fix using owned assets"
    return result


def _sanitize_fix_tv_claims(
    fix: dict[str, Any],
    *,
    tv_catalog: dict[str, float],
) -> dict[str, Any]:
    if not tv_catalog:
        return fix

    warnings: list[str] = []
    valid_adjustments: list[str] = []
    dropped_adjustments: list[str] = []
    for adjustment in fix.get("adjustments") or []:
        adj_text = str(adjustment)
        upgrade = _give_pick_upgrade_substitution(adj_text, tv_catalog)
        if upgrade:
            dropped_adjustments.append(adj_text)
            if upgrade not in warnings:
                warnings.append(upgrade)
            continue
        valid_adjustments.append(adj_text)

    reasoning = str(fix.get("reasoning") or "")
    for text in [reasoning, *dropped_adjustments]:
        warning = _inverted_pick_swap_claim(text, tv_catalog)
        if warning and warning not in warnings:
            warnings.append(warning)

    if not warnings and not dropped_adjustments:
        return fix

    result = dict(fix)
    result["adjustments"] = valid_adjustments
    result["both_sides_likely_accept"] = False
    if dropped_adjustments:
        drop_note = (
            "Removed give-package pick upgrades (earlier pick = higher TV): "
            + "; ".join(dropped_adjustments[:2])
        )
        warnings.insert(0, drop_note)
    note = " ".join(warnings)
    reasoning_out = str(result.get("reasoning") or "").strip()
    result["reasoning"] = f"{reasoning_out} ({note})" if reasoning_out else note
    if not valid_adjustments and not result.get("headline"):
        result["headline"] = "No valid TV-reducing fix"
    return result


def _compact_side_validation_for_fix(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "accept_likelihood": validation.get("accept_likelihood"),
        "fairness_view": validation.get("fairness_from_counterparty_view"),
        "would_improve_roster": validation.get("would_improve_their_roster"),
        "reasoning": validation.get("reasoning"),
        "blockers": validation.get("blockers") or [],
        "suggested_tweak": validation.get("suggested_tweak"),
    }


def build_fix_payload(
    *,
    side_a_team: dict[str, Any],
    side_b_team: dict[str, Any],
    give: dict[str, Any],
    receive: dict[str, Any],
    tv_evaluation: dict[str, Any],
    side_a_validation: dict[str, Any],
    side_b_validation: dict[str, Any],
    rookie_draft_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    a_name = str(side_a_team.get("team_name") or "Side A")
    b_name = str(side_b_team.get("team_name") or "Side B")
    inventory_a = _tradable_inventory(side_a_team)
    inventory_b = _tradable_inventory(side_b_team)
    give_adj = float(tv_evaluation.get("give_adjusted_tv") or 0)
    recv_adj = float(tv_evaluation.get("receive_adjusted_tv") or 0)
    pick_tv = _pick_tv_catalog(inventory_a, inventory_b)
    for pick in (give.get("picks") or []) + (receive.get("picks") or []):
        label = _normalize_pick_label(str(pick.get("label") or ""))
        tv = pick.get("trade_value") or pick.get("tv")
        if label and tv is not None:
            pick_tv.setdefault(label, float(tv))
    payload: dict[str, Any] = {
        "side_a_team": _compact_team_context(side_a_team),
        "side_b_team": _compact_team_context(side_b_team),
        "tradable_inventory": {
            a_name: inventory_a,
            b_name: inventory_b,
        },
        "tv_by_side": {
            a_name: _team_tv_summary(gives_adj=give_adj, receives_adj=recv_adj),
            b_name: _team_tv_summary(gives_adj=recv_adj, receives_adj=give_adj),
        },
        "pick_tv_catalog": pick_tv,
        "trade_package": {
            a_name: {
                "gives": {
                    "players": [_compact_player(p) for p in give.get("players") or []],
                    "picks": [_compact_pick(p) for p in give.get("picks") or []],
                },
                "receives": {
                    "players": [_compact_player(p) for p in receive.get("players") or []],
                    "picks": [_compact_pick(p) for p in receive.get("picks") or []],
                },
            },
            b_name: {
                "gives": {
                    "players": [_compact_player(p) for p in receive.get("players") or []],
                    "picks": [_compact_pick(p) for p in receive.get("picks") or []],
                },
                "receives": {
                    "players": [_compact_player(p) for p in give.get("players") or []],
                    "picks": [_compact_pick(p) for p in give.get("picks") or []],
                },
            },
        },
        "picks_given_in_trade": {
            a_name: sorted(
                _normalize_pick_label(str(p.get("label") or ""))
                for p in give.get("picks") or []
                if str(p.get("label") or "").strip()
            ),
            b_name: sorted(
                _normalize_pick_label(str(p.get("label") or ""))
                for p in receive.get("picks") or []
                if str(p.get("label") or "").strip()
            ),
        },
        "tv_evaluation": {
            "net_adjusted_total_tv_delta": tv_evaluation.get("net_delta_adjusted_total_tv"),
            "net_adjusted_total_tv_pct": tv_evaluation.get("net_delta_adjusted_pct"),
            "within_band": tv_evaluation.get("within_band"),
            "tv_favors": tv_evaluation.get("favors_roster_id"),
            "tv_fairness_grade": tv_evaluation.get("tv_fairness_grade"),
        },
        "side_a_validation": _compact_side_validation_for_fix(side_a_validation),
        "side_b_validation": _compact_side_validation_for_fix(side_b_validation),
    }
    payload["pick_downgrade_options"] = _pick_downgrade_options(
        trade_package=payload["trade_package"],
        tradable_inventory=payload["tradable_inventory"],
        pick_tv_catalog=pick_tv,
    )
    if rookie_draft_context:
        payload["rookie_draft_context"] = rookie_draft_context
    return payload


def _normalize_fix(parsed: dict[str, Any]) -> dict[str, Any]:
    adjustments = parsed.get("adjustments") or []
    if not isinstance(adjustments, list):
        adjustments = [str(adjustments)]
    return {
        "headline": str(parsed.get("headline") or "").strip() or None,
        "reasoning": str(parsed.get("reasoning") or "").strip() or None,
        "adjustments": [str(a).strip() for a in adjustments if str(a).strip()],
        "both_sides_likely_accept": bool(parsed.get("both_sides_likely_accept")),
    }


def suggest_trade_fix_with_llm(
    payload: dict[str, Any],
    *,
    api_key: str | None,
    model: str | None = None,
) -> dict[str, Any]:
    """Third LLM pass: suggest a fix both sides might accept."""
    if not api_key or not api_key.strip():
        return {
            "error": "ANTHROPIC_API_KEY not configured — trade fix skipped",
            "skipped": True,
        }

    resolved_model = model or get_settings().llm_validation_model or DEFAULT_VALIDATION_MODEL
    client = anthropic.Anthropic(api_key=api_key.strip())
    response = create_message(
        client,
        feature="trade_fix",
        model=resolved_model,
        max_tokens=700,
        system=_FIX_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": json.dumps(payload, indent=2, default=str),
            }
        ],
    )
    text_parts = [
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ]
    raw_text = "".join(text_parts)
    parsed = _parse_validation_json(raw_text)
    normalized = _normalize_fix(parsed)
    sanitized = _sanitize_fix_against_inventory(
        normalized,
        tradable_inventory=payload.get("tradable_inventory") or {},
        trade_package=payload.get("trade_package") or {},
    )
    return _sanitize_fix_tv_claims(
        sanitized,
        tv_catalog=payload.get("pick_tv_catalog") or {},
    )


def _compact_player(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row.get("name") or row.get("player_name"),
        "position": row.get("position") or row.get("pos"),
        "tv": row.get("tv") or row.get("trade_value"),
        "hppg": row.get("hppg"),
        "ovr": row.get("ovr"),
        "age": row.get("age"),
        "trade_tag": row.get("trade_tag"),
        "depth_rank": row.get("depth_rank"),
        "lineup_delta_ppg": row.get("lineup_delta_ppg"),
    }


def _player_roster_index(team: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in team.get("players") or []:
        pid = row.get("player_id")
        if pid:
            index[str(pid)] = row
    return index


def _enrich_trade_players(
    players: list[dict[str, Any]],
    roster_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for player in players:
        row = dict(player)
        pid = str(row.get("player_id") or "")
        roster_row = roster_index.get(pid) if pid else None
        if roster_row:
            for key in ("lineup_delta_ppg", "trade_tag", "depth_rank", "age", "hppg", "ovr"):
                if row.get(key) is None and roster_row.get(key) is not None:
                    row[key] = roster_row.get(key)
        enriched.append(_compact_player(row))
    return enriched


def _compact_lineup_starter(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot": row.get("slot"),
        "name": row.get("name"),
        "position": row.get("position"),
        "ppg": row.get("ppg"),
        "ovr": row.get("ovr"),
        "is_incoming": bool(row.get("is_incoming")),
        "is_changed": bool(row.get("is_changed")),
    }


def _compact_lineup_side(side: dict[str, Any] | None) -> dict[str, Any] | None:
    if not side:
        return None
    return {
        "starter_ppg_before": side.get("before"),
        "starter_ppg_after": side.get("after"),
        "starter_ppg_delta": side.get("delta"),
        "post_trade_starters": [
            _compact_lineup_starter(slot) for slot in (side.get("starters") or [])
        ],
        "incoming_picks": [
            _compact_pick(pick) for pick in (side.get("incoming_picks") or [])
        ],
    }


def _compact_team_context(team: dict[str, Any]) -> dict[str, Any]:
    return {
        "team_name": team.get("team_name"),
        "contender_tier": team.get("contender_tier"),
        "dynasty_rank": team.get("dynasty_rank"),
        "starter_total_ppg": team.get("starter_total_ppg"),
        "surplus": team.get("surplus") or [],
        "needs": team.get("needs") or [],
        "starter_needs": team.get("starter_needs") or [],
        "draft_picks": [
            _compact_pick(pick) for pick in (team.get("draft_picks") or [])[:8]
        ],
    }


def _compact_pick(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": row.get("label"),
        "season": row.get("season"),
        "round": row.get("round"),
        "tv": row.get("trade_value") or row.get("tv"),
        "slot_tier": row.get("slot_tier"),
        "trade_tag": row.get("trade_tag"),
        "is_own_slot": row.get("is_own_slot"),
    }


def _review_team_tv_summary(
    give: dict[str, Any],
    receive: dict[str, Any],
    tv_evaluation: dict[str, Any],
    *,
    review_team_name: str,
    other_team_name: str,
    review_team_index: dict[str, dict[str, Any]],
    other_team_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """TV math from review_for_team's perspective (review gives receive-side assets)."""
    other_gives = float(tv_evaluation.get("give_total_tv") or 0)
    other_receives = float(tv_evaluation.get("receive_total_tv") or 0)
    other_gives_adj = float(tv_evaluation.get("give_adjusted_tv") or 0)
    other_receives_adj = float(tv_evaluation.get("receive_adjusted_tv") or 0)

    review_gives = other_receives
    review_gets = other_gives
    review_gives_adj = other_receives_adj
    review_gets_adj = other_gives_adj

    net_raw = review_gets - review_gives
    net_adj = review_gets_adj - review_gives_adj
    raw_total = tv_evaluation.get("net_delta_adjusted_total_tv")
    if raw_total is not None:
        net_adj_total = -float(raw_total)
    else:
        net_adj_total = net_adj

    if tv_evaluation.get("within_band"):
        tv_favors = "fair"
    elif net_adj_total > 0:
        tv_favors = review_team_name
    elif net_adj_total < 0:
        tv_favors = other_team_name
    else:
        tv_favors = "fair"

    return {
        "gives": {
            "players": _enrich_trade_players(
                receive.get("players") or [],
                review_team_index,
            ),
            "picks": [_compact_pick(pick) for pick in receive.get("picks") or []],
            "total_tv": round(review_gives, 2),
            "adjusted_tv": round(review_gives_adj, 2),
        },
        "gets": {
            "players": _enrich_trade_players(
                give.get("players") or [],
                other_team_index,
            ),
            "picks": [_compact_pick(pick) for pick in give.get("picks") or []],
            "total_tv": round(review_gets, 2),
            "adjusted_tv": round(review_gets_adj, 2),
        },
        "net_tv_delta": round(net_raw, 2),
        "net_adjusted_tv_delta": round(net_adj, 2),
        "net_adjusted_total_tv_delta": round(net_adj_total, 2),
        "net_adjusted_total_tv_pct": round(
            -float(tv_evaluation.get("net_delta_adjusted_pct") or 0), 2
        ),
        "tv_favors": tv_favors,
        "within_band": tv_evaluation.get("within_band"),
        "consolidation_tax_tv": tv_evaluation.get("consolidation_tax_tv"),
        "other_team_pays_consolidation_tax": bool(tv_evaluation.get("receive_consolidating")),
    }


def _counterparty_tv_summary(
    give: dict[str, Any],
    receive: dict[str, Any],
    tv_evaluation: dict[str, Any],
    *,
    proposer_index: dict[str, dict[str, Any]],
    counterparty_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Backward-compatible alias used in tests."""
    return _review_team_tv_summary(
        give,
        receive,
        tv_evaluation,
        review_team_name="counterparty",
        other_team_name="proposer",
        review_team_index=counterparty_index,
        other_team_index=proposer_index,
    )


def _fairness_label_for_counterparty(
    fairness: str | None,
    *,
    counterparty_name: str,
    proposer_name: str,
) -> str:
    key = str(fairness or "fair").lower()
    cp = counterparty_name or "them"
    prop = proposer_name or "opponent"
    if key == "favors_them":
        return f"Favors {cp}"
    if key == "favors_you":
        return f"Favors {prop}"
    return "Fair"


def build_validation_payload(
    *,
    proposer_roster_id: str,
    counterparty_roster_id: str,
    proposer_team: dict[str, Any],
    counterparty_team: dict[str, Any],
    give: dict[str, Any],
    receive: dict[str, Any],
    tv_evaluation: dict[str, Any],
    proposer_lineup: dict[str, Any] | None = None,
    counterparty_lineup: dict[str, Any] | None = None,
    rookie_draft_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shape context for the validation LLM."""
    proposer_index = _player_roster_index(proposer_team)
    counterparty_index = _player_roster_index(counterparty_team)
    review_name = str(counterparty_team.get("team_name") or counterparty_roster_id)
    other_name = str(proposer_team.get("team_name") or proposer_roster_id)

    payload: dict[str, Any] = {
        "review_for_team": review_name,
        "the_other_team": other_name,
        "review_for_team_context": {
            "roster_id": counterparty_roster_id,
            **_compact_team_context(counterparty_team),
            "top_players": [
                _compact_player(player)
                for player in (counterparty_team.get("players") or [])[:12]
            ],
        },
        "the_other_team_context": {
            "roster_id": proposer_roster_id,
            **_compact_team_context(proposer_team),
        },
        "review_for_team_trade": {
            "gives": {
                "players": _enrich_trade_players(
                    receive.get("players") or [],
                    counterparty_index,
                ),
                "picks": [_compact_pick(pick) for pick in receive.get("picks") or []],
            },
            "gets": {
                "players": _enrich_trade_players(
                    give.get("players") or [],
                    proposer_index,
                ),
                "picks": [_compact_pick(pick) for pick in give.get("picks") or []],
            },
        },
        "review_for_team_tv": _review_team_tv_summary(
            give,
            receive,
            tv_evaluation,
            review_team_name=review_name,
            other_team_name=other_name,
            review_team_index=counterparty_index,
            other_team_index=proposer_index,
        ),
    }

    lineup_impact: dict[str, Any] = {}
    counterparty_lineup_compact = _compact_lineup_side(counterparty_lineup)
    proposer_lineup_compact = _compact_lineup_side(proposer_lineup)
    if counterparty_lineup_compact is not None:
        lineup_impact[review_name] = counterparty_lineup_compact
    if proposer_lineup_compact is not None:
        lineup_impact[other_name] = proposer_lineup_compact
    if lineup_impact:
        payload["lineup_impact"] = lineup_impact
    if rookie_draft_context:
        payload["rookie_draft_context"] = rookie_draft_context

    payload["tradable_inventory"] = {
        str(counterparty_team.get("team_name") or counterparty_roster_id): {
            "pick_labels": _tradable_inventory(counterparty_team)["pick_labels"],
            "player_names": _tradable_inventory(counterparty_team)["player_names"],
        },
        str(proposer_team.get("team_name") or proposer_roster_id): {
            "pick_labels": _tradable_inventory(proposer_team)["pick_labels"],
            "player_names": _tradable_inventory(proposer_team)["player_names"],
        },
    }

    return payload


def _parse_validation_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match is None:
            raise ValueError("validation response was not JSON")
        return json.loads(match.group(0))


def _resolve_labeled_side(
    side: dict[str, Any] | None,
    *,
    team: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map LLM counter_offer player names / pick labels to roster rows."""
    if not side:
        return [], []
    inventory = _tradable_inventory(team)
    players_by_name = inventory.get("players_by_name") or {}
    pick_by_label = {
        _normalize_pick_label(str(pick.get("label") or "")): pick
        for pick in (team.get("draft_picks") or [])
        if pick.get("label")
    }

    resolved_players: list[dict[str, Any]] = []
    for raw_name in side.get("players") or []:
        name = str(raw_name or "").strip()
        if not name:
            continue
        row = players_by_name.get(name.lower())
        if row is None:
            for key, candidate in players_by_name.items():
                if name.lower() in key or key in name.lower():
                    row = candidate
                    break
        if row is not None:
            resolved_players.append(dict(row))

    resolved_picks: list[dict[str, Any]] = []
    for raw_label in side.get("picks") or []:
        label = _normalize_pick_label(str(raw_label or ""))
        if not label:
            continue
        pick = pick_by_label.get(label)
        if pick is None:
            for pick_label, row in pick_by_label.items():
                if pick_label.lower() == label.lower():
                    pick = row
                    break
        if pick is not None:
            resolved_picks.append(dict(pick))

    return resolved_players, resolved_picks


def _counter_offer_owned_by_team(
    side: dict[str, Any] | None,
    *,
    team: dict[str, Any],
) -> bool:
    if not side:
        return True
    inventory = _tradable_inventory(team)
    owned_picks = set(inventory.get("pick_labels") or [])
    owned_players = {n.lower() for n in (inventory.get("player_names") or [])}
    for raw_label in side.get("picks") or []:
        label = _normalize_pick_label(str(raw_label or ""))
        if label and label not in owned_picks:
            return False
    for raw_name in side.get("players") or []:
        name = str(raw_name or "").strip().lower()
        if name and name not in owned_players:
            return False
    return True


def resolve_counter_offer_package(
    counter_offer: dict[str, Any] | None,
    *,
    proposer_team: dict[str, Any],
    counterparty_team: dict[str, Any],
) -> dict[str, Any] | None:
    """Turn validator counter_offer into a resolved give/receive package."""
    if not counter_offer or not isinstance(counter_offer, dict):
        return None

    proposer_gives = counter_offer.get("proposer_gives") or {}
    proposer_receives = counter_offer.get("proposer_receives") or {}
    if not _counter_offer_owned_by_team(proposer_gives, team=proposer_team):
        return None
    if not _counter_offer_owned_by_team(proposer_receives, team=counterparty_team):
        return None

    give_players, give_picks = _resolve_labeled_side(proposer_gives, team=proposer_team)
    recv_players, recv_picks = _resolve_labeled_side(proposer_receives, team=counterparty_team)
    if not (give_players or give_picks or recv_players or recv_picks):
        return None

    return {
        "give": {"players": give_players, "picks": give_picks},
        "receive": {"players": recv_players, "picks": recv_picks},
        "rationale": str(counter_offer.get("rationale") or "").strip() or None,
        "source": "validator_counter_offer",
    }


def heuristic_validation_skip(pkg: dict[str, Any]) -> dict[str, Any] | None:
    """Skip LLM when TV math already shows an obvious lowball."""
    pct = float(pkg.get("net_delta_adjusted_pct") or 0)
    if pct <= 5.0:
        return None
    return {
        "accept_likelihood": "low",
        "fairness_from_counterparty_view": "favors_you",
        "would_improve_their_roster": False,
        "reasoning": (
            "Adjusted TV favors the proposer by more than 5% — the counterparty is giving up "
            "more value than they receive on paper."
        ),
        "blockers": ["TV lowball — counterparty loses adjusted value"],
        "suggested_tweak": "Add value to the proposer's offer or request pick/player sweeteners back.",
        "counter_offer": None,
        "heuristic": True,
        "skipped_llm": True,
    }


def _normalize_validation(parsed: dict[str, Any]) -> dict[str, Any]:
    likelihood = str(parsed.get("accept_likelihood") or "medium").lower()
    if likelihood not in ("low", "medium", "high"):
        likelihood = "medium"
    fairness = str(parsed.get("fairness_from_counterparty_view") or "fair").lower()
    if fairness not in ("favors_them", "fair", "favors_you"):
        fairness = "fair"
    blockers = parsed.get("blockers") or []
    if not isinstance(blockers, list):
        blockers = [str(blockers)]
    tweak = parsed.get("suggested_tweak")
    counter_offer = parsed.get("counter_offer")
    if likelihood == "high":
        counter_offer = None
    elif not isinstance(counter_offer, dict):
        counter_offer = None
    return {
        "accept_likelihood": likelihood,
        "fairness_from_counterparty_view": fairness,
        "would_improve_their_roster": bool(parsed.get("would_improve_their_roster")),
        "reasoning": str(parsed.get("reasoning") or "").strip(),
        "blockers": [str(b).strip() for b in blockers if str(b).strip()],
        "suggested_tweak": str(tweak).strip() if tweak else None,
        "counter_offer": counter_offer,
    }


def validate_trade_with_llm(
    payload: dict[str, Any],
    *,
    api_key: str | None,
    model: str | None = None,
) -> dict[str, Any]:
    """Run counterparty-perspective validation. Requires Anthropic API key."""
    if not api_key or not api_key.strip():
        return {
            "error": "ANTHROPIC_API_KEY not configured — validation skipped",
            "skipped": True,
        }

    resolved_model = model or get_settings().llm_validation_model or DEFAULT_VALIDATION_MODEL
    client = anthropic.Anthropic(api_key=api_key.strip())
    response = create_message(
        client,
        feature="trade_validation",
        model=resolved_model,
        max_tokens=1100,
        system=_VALIDATION_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": json.dumps(payload, indent=2, default=str),
            }
        ],
    )
    text_parts = [
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ]
    raw_text = "".join(text_parts)
    parsed = _parse_validation_json(raw_text)
    return _normalize_validation(parsed)
