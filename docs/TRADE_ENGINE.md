# Trade engine — expendability & package valuation

Design for in-season trade suggestions and `evaluate_trade`. Replaces naive `sum(TV)` fairness with roster-context scores and consolidation-aware package math.

## Problems

1. **Position surplus ≠ player expendability** — `trade_surplus` is team-level (starter avg OVR rank). A WR1 on a WR-strong team should not surface as a sell candidate.
2. **Strategy mismatch** — Contenders move vets; rebuilders move aging win-now pieces and hoard youth. `contender_tier` existed but was not used in deterministic trades.
3. **Linear TV sums** — Ten 1k assets do not equal one 10k asset. Packages need depth discount + consolidation premium.

## Concepts

| Term | Meaning |
|------|---------|
| **Expendability** | 0–100 score: how movable is this player *on your roster*? High = depth/surplus/replaceable. Low = core piece. |
| **Trade fit** | 0–1 score: how much does a *counterparty* want this player given their needs, surplus, and tier? |
| **Raw TV** | `sum(asset.trade_value)` — market anchor, unchanged. |
| **Effective TV** | Package value after depth discount + piece-count penalty. |
| **Adjusted TV** | Effective TV × consolidation premium on the side acquiring fewer/higher assets. |

## Expendability (per player)

Inputs (all available at sync):

| Signal | Weight | Rule |
|--------|--------|------|
| Depth rank | 45% | TV rank within position on roster: WR1 ≈ 0.05 … WR4+ ≈ 1.0 |
| Surplus leverage | 35% | 1.0 if team `trade_surplus` lists position as surplus, else 0.35 |
| Replaceability | 20% | `1 − (tv − next_best_tv) / tv` — small gap to backup = easier to move |

**Strategy multiplier** (`contender_tier`):

- **Contender** — boost sell score for age ≥ 28 with HPPG ≥ 10; penalize age ≤ 24 with OVR ≥ 82.
- **Rebuild** — boost age ≥ 28; penalize age ≤ 23 with OVR ≥ 78.
- **Competitive** — neutral.

Final: `expendability = clamp(weighted_sum × strategy_mult × 100, 0, 100)`.

Starters (depth rank 1) stay low unless rebuild + aging vet.

## Trade fit (pairwise)

Base 0.5, then:

- +0.35 if player position is in acquirer **needs**
- −0.25 if in acquirer **surplus**
- +0.15 contender + age ≥ 25 + HPPG ≥ 10 (win-now piece)
- +0.15 rebuild + age ≤ 24 (youth)
- +0.10 cross-tier: rebuild→contender vet, contender→rebuild youth

Used to rank receive targets in `suggest_trades`.

## Package valuation

### Depth discount + piece penalty

```text
effective = (top_tv + 0.70 × sum(other_tvs)) × 0.95^(n−1)
```

Single-asset packages: `effective = tv`.

Picks count as assets (use `trade_value`).

### Consolidation premium (12%)

Side that **consolidates** (fewer player assets, or same count but higher max TV) must overpay in raw TV:

```text
consolidation_tax = receive_raw × 12%   (when you acquire the stud)
net_adjusted = (receive_raw − give_raw) − consolidation_tax
```

Fairness band (±5%) applies to `net_adjusted`, not raw sum alone. Effective TV is still reported so the advisor can explain depth discount separately.

`evaluate_trade` returns both raw and effective/adjusted columns so the advisor can narrate: “Fair on KTC totals, but you’re consolidating — need a bit more.”

## `suggest_trades` flow

1. Counterparties from `trade_surplus` (unchanged).
2. **Give pool** — top expendability at hook position (not blind depth slice).
3. **Receive pool** — rank by `fit × tv`.
4. Build 1-for-1 or 2-for-2; balance with one pick using **effective** TV.
5. Score package: `avg_expendability × avg_fit / (1 + |net_delta_adjusted_pct|/10)`.
6. Return top 5 by quality (not closest raw TV).

## API surfaces

| Surface | Fields added |
|---------|----------------|
| `get_team` | `expendability_score` per player; `trade_candidates` top 5 sell candidates |
| `evaluate_trade` | `give_effective_tv`, `receive_effective_tv`, `consolidation_tax_tv`, `net_delta_adjusted_pct` |
| `suggest_trades` | `package_quality`, `expendability`, `trade_fit`, effective fairness fields |

## Constants (tune in `trade_engine.py`)

```python
DEPTH_TV_DISCOUNT = 0.70
PIECE_COUNT_PENALTY = 0.95
CONSOLIDATION_PREMIUM = 0.12
FAIRNESS_BAND = 0.05
MIN_EXPENDABILITY_TO_SELL = 0.30  # fraction 0–1 before ×100 display
```

## Future (not in v1)

- **Marginal lineup delta** — value trade via optimal-lineup before/after (replaces depth rank for expendability).
- **Empirical calibration** — fit consolidation premium from logged real trades.
- **UI** — expendability badge on roster table / player card (shipped 2026-06).

## References

- `backend/services/trade_engine.py` — pure functions
- `backend/services/advisor_tools.py` — tool wiring
- `backend/services/analysis_service.py` — `trade_surplus`, `contender_index`
- Tests: `tests/test_trade_engine.py`, `tests/test_advisor_tools.py`
