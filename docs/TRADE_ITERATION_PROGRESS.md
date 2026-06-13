# Trade iteration progress

Living doc for GLA trade-engine work, Sleeper pick debugging, and local dev. Update as we iterate.

**League:** Good Luck Assholes (`1314731206859853824`)  
**Team:** The Process — roster **3**, contender, dynasty rank **1**  
**Last updated:** 2026-06-13

---

## Current status

| Area | Status | Notes |
|------|--------|-------|
| Pick labeling (1.01 vs 1.10) | **Fixed locally** | Startup draft slot drives pre-season picks |
| `collect_league_traded_picks` | **Fixed locally** | Merges league + draft `traded_picks` (2026 on startup draft) |
| KTC stud adjustment | **Local** | `stud_value_adjustment()` in `trade_engine.py` |
| Targeted trade suggester | **Built (local)** | `target_player_id` / `target_position`; acquisition overpay band |
| Core tag tail-depth bug | **Fixed** | Last player on depth chart → delta 0 (not full PPG) |
| Production resync | **Done (local)** | Sync run #113; roster 3 shows 2026 1.01/2.01/3.01 |
| Local Postgres (Docker) | **Up** | `dc-postgres-1` on port 5444; migrations at head |

---

## Sleeper pick investigation (2026-06-13)

### What Sleeper shows (roster 3)

Screenshot matches our corrected model:

- 2026 **1.01**, **2.01**, **3.01** (own franchise slots)
- League: pre_draft, season 2026, 10-team dynasty SF

### Root cause we had wrong

Sleeper’s **1.01** is **rookie-draft slot within the round**, derived from **startup player-draft order** — not `original_roster_id` in `traded_picks` and not dynasty rank.

- Roster 3 had **startup draft slot #10** (last in 23-round snake `1314734674332880896`)
- Formula: `pick_in_round = league_size + 1 - startup_draft_slot` → **1.01, 2.01, 3.01**
- We were using dynasty rank **#1** (best team) → **1.10 / late tier** — wrong pre-season

### Verified startup slots (2026-06-13 API pull)

| Roster | Startup slot | 2026 R1 slot |
|--------|--------------|--------------|
| 5 | 1 | 1.10 |
| 4 | 2 | 1.09 |
| 2 | 3 | 1.08 |
| 7 | 4 | 1.07 |
| 8 | 5 | 1.06 |
| 10 | 6 | 1.05 |
| 6 | 7 | 1.04 |
| 1 | 8 | 1.03 |
| 9 | 9 | 1.02 |
| **3** | **10** | **1.01** |

### Pick data sources in Sleeper

| Source | Seasons | Notes |
|--------|---------|-------|
| League `traded_picks` | 2027–2028 | 11 entries |
| Startup draft `traded_picks` | 2026 | 10 entries on draft `1314734674332880896` |
| Pick allocation draft | — | `1370865581258989568`, pre_draft, not yet run |

`collect_league_traded_picks()` merges league + all draft `traded_picks` (21 total after dedupe).

### Code fix

- `startup_draft_slot_by_roster()` — from completed snake startup draft `draft_order`
- `_use_startup_slots_for_season()` — when league `pre_draft`/`drafting`, current season uses startup slots
- `slot_in_round()` / `infer_slot_tier()` accept `startup_draft_slot` in `inseason_pick_values.py`
- Own current-season picks get `slot_certainty = "known"`

---

## Trade suggester — known gaps

`generate_trade_suggestions` (`advisor_tools.py`):

- No target player/position — only `trade_surplus` counterparty hooks
- Give pool = Trade-tagged only; fairness ±5% raw TV
- Escalates to 2-for-2 + pick; can produce absurd packages (+40% adjusted TV)
- `validate_trade` correctly flags low `accept_likelihood`

**Agreed direction (backlog):**

- User specifies target position or player (e.g. Omarion Hampton, roster 4)
- Acquisition mode: KTC adjustment + overpay tolerance for studs
- Stud-for-stud + picks (1sts almost always involved)
- Example package user likes: **1.01 + 2026 2.01 → Hampton + 2027 1st**

**Hampton:** `player_id` 12507, roster **4** (BunnyInTheBox). Resync if stale in DB.

---

## Local iteration commands

```bash
uv run python scripts/run_trade_iteration.py --db
uv run python scripts/run_trade_iteration.py --db --player 12507   # Hampton
uv run python scripts/run_trade_iteration.py --db --position RB   # league-wide key RB scan
uv run python scripts/run_trade_iteration.py --db --target 4 --validate
```

Tests: `uv run pytest tests/test_trade_engine.py tests/test_acquisition_trades.py tests/test_pick_draft_merge.py`

---

## Docker / Postgres (2026-06-13)

**Resolved after reboot.** Docker Desktop was stuck pre-reboot (CLI hung on daemon socket).

```bash
cd /Users/afautsch/dc
docker compose up -d postgres   # dc-postgres-1 → localhost:5444
uv run alembic upgrade head     # at head as of 2026-06-13
```

Other containers on machine: `mia-postgres` (5432), `mia-pgadmin` (8080).

**Stale plugin warning (cosmetic):** `docker-dev` CLI plugin symlink broken — does not block compose.

---

## Shipped to main (prior commits)

| Commit | Content |
|--------|---------|
| `38761a5` | Trade v2: lineup_delta_ppg, Core/Trade tags, pick slot notation |
| `63d8c7d` | Opt-in `validate_trade` + `trade_validation_service.py` |

## Local changes not yet pushed

- `backend/services/pick_service.py` — startup slots + restored `collect_league_traded_picks`
- `dynasty_draft/inseason_pick_values.py` — startup slot params, certainty, contender bump
- `backend/services/trade_engine.py` — KTC stud adjustment (if present)
- `tests/test_pick_draft_merge.py`, `tests/test_trade_engine.py`

---

## Next steps

1. [x] Docker + Postgres up on 5444
2. [ ] Commit + push pick-slot fix (confirm with user)
3. [x] Resync GLA; verify roster 3 shows 2026 1.01/2.01/3.01 in app
4. [x] Build targeted trade generator (`--player` / `--position`)
5. [x] Filter absurd adjusted-TV gaps on surplus path; core targets require a 1st
6. [ ] Commit + push pick-slot + acquisition fixes (confirm with user)
7. [ ] Tune acquisition templates (e.g. 1.01 + 2.01 → stud + 1st)
8. [ ] Resync production Railway after push

---

## Key files

| Path | Role |
|------|------|
| `backend/services/pick_service.py` | Pick sync, startup slots, draft merge |
| `dynasty_draft/inseason_pick_values.py` | Pick TV, slot notation |
| `backend/services/trade_engine.py` | Tagging, KTC adjustment |
| `backend/services/advisor_tools.py` | `suggest_trades`, `validate_trade` |
| `scripts/run_trade_iteration.py` | Local iteration CLI |
| `docs/TRADE_ENGINE.md` | Design spec |
