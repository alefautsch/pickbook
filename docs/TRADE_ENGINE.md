# Trade engine — lineup value, picks, and package valuation

## Problem

Linear TV and depth rank alone mis-tag players (e.g. WR2 with 18 PPG tagged "Move" while a 10 PPG backup sits behind him). Dynasty trades also run on **draft picks** — stable currency whose value differs by contender vs rebuild.

## v2 tagging (2026-06)

Only **Core** and **Trade** tags surface in the UI. ~70–85% of roster has no tag.

### Player signals

| Field | Meaning |
|-------|---------|
| `production_ppg` | 65% HPPG + 35% projected PPG (recent results weighted) |
| `lineup_delta_ppg` | Marginal PPG vs next backup at position (production order, not TV) |
| `tv_vs_production_gap` | TV percentile − production percentile within position (sell-high when large) |
| `trade_tag` | `core` \| `trade` \| null |

### Core (do not sell)

- `lineup_delta_ppg` ≥ threshold (contender **6.0**, competitive **5.0**, rebuild **4.0**)
- Or #1 by production with meaningful cliff

### Trade (sell chip)

**Contenders** — consolidate depth, ship picks:

- Surplus position, depth ≥ 3, low marginal PPG
- Sell-high: TV ≫ production, age 26+
- Depth ≥ 4–6 with replaceable production

**Rebuilders** — hoard picks, move vets:

- Age 28+ with low marginal value
- Surplus depth rank ≥ 4
- Depth rank ≥ 5

### Draft picks

Picks are first-class assets with slot-specific TV:

- **Season window** includes current league year (fixes missing 2026 picks mid-season)
- **Slot notation**: `2026 1.01` from original owner's dynasty rank
- **Premium**: top-3 round-1 early slots (1.01 ≈ elite rookie class) get +10–28% TV

| Strategy | Pick tagging |
|----------|----------------|
| Rebuild | **Core**: early/mid 1sts, early 2nds · **Trade**: late 2nds+, round 3+ |
| Contender | **Trade**: own-slot round 1–3 (ship for win-now) · acquired early 1sts untagged |
| Competitive | Own late 2nds+ trade · acquired early 1sts core |

`trade_candidates` on team page includes **players and picks** tagged Trade.

## Trade patterns (v3 — 2026-06)

The engine builds packages from a few dynasty-native patterns:

| Pattern | Shape | Example |
|---------|--------|---------|
| `same_position_upgrade` | ~90% player + pick sweeteners | Kraft + 2.01 + 3.01 → Loveland |
| `need_swap_with_depth` | surplus + depth @ their need → stud + depth @ your surplus | McMillan + Etienne → Hampton + Brian Thomas |
| `pick_lubricant` | future/current picks without 1.01 | 2.01 + 2027 1st → Hampton |

CLI: `uv run python scripts/run_trade_iteration.py --db --swap --need RB --player 12507`

## Package valuation (unchanged)

- `effective_package_tv` — depth discount (0.70) + piece penalty (0.95^n)
- Consolidation tax — ~12% raw TV overpay to acquire the stud side
- `suggest_trades` give pool = **Trade-tagged only** (players + picks)

## API surfaces

| Endpoint / tool | Fields |
|-----------------|--------|
| `get_team` | `trade_tag`, `lineup_delta_ppg` per player; `trade_tag` per pick; `trade_candidates` |
| `get_player` | `trade_tag`, `lineup_delta_ppg`, `tv_vs_production_gap` |
| `suggest_trades` | Trade-tagged give assets; strategy-aware pick inclusion |
| `evaluate_trade` | Raw + effective TV + consolidation tax |
| `validate_trade` | Opt-in LLM counterparty accept/reject judgment |

## Deprecated

`expendability_score` and Move/Depth labels are legacy; UI uses `trade_tag` only.
