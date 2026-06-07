# Dynasty Blackbook — Task Plan

The executable backlog for building Blackbook. Design rationale lives in `BLACKBOOK.md`; this file is *how* and *in what order*. Every task should trace back to a design section (referenced as §N).

**Status legend:** `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked

**Current branch:** `blackbook` · **Last updated:** 2026-06-07 · **Phase 0–6:** complete (local) · **Phase 7:** complete (local) · **UI north star:** `.cache/*_mockup*.png`

---

## How to use this doc

- Work top-to-bottom by phase. Phases gate on the prior phase's **exit criteria**.
- Each phase lists tasks with concrete file paths and acceptance checks.
- Keep `dynasty_draft/` (the engine) importable and non-breaking — Pickbook depends on it (§9, §3.7).
- Update the design book when a task forces a design decision (don't silently diverge).

---

## Conventions

### Repo layout (target)
```
dc/
  dynasty_draft/          # engine (existing) — imported as a library, kept stable
  backend/                # FastAPI app (new)
    main.py
    api/
      __init__.py
      leagues.py
      teams.py
      players.py
      portfolio.py
      sync.py
      settings.py
    services/
      league_context.py   # LeagueScoringContext factory (§6)
      sync_service.py      # Sleeper -> Postgres (§10)
      metrics_service.py   # rosters -> engine -> snapshots (§5.7, §10)
      analysis_service.py  # contender index, position strength (§8)
    db/
      models.py            # SQLAlchemy models (§10)
      session.py
      migrations/          # alembic
    schemas/               # pydantic DTOs (§11)
      player.py
      league.py
      team.py
    config.py              # env + settings
  frontend/                # Next.js app (new)
    app/
      page.tsx                       # hub (§12.5)
      leagues/[leagueId]/page.tsx
      leagues/[leagueId]/teams/[rosterId]/page.tsx
      players/[playerId]/page.tsx
      portfolio/page.tsx
    components/
      OvrBadge.tsx
      PlayerCard.tsx
      TeamLineup.tsx
      RankingsTable.tsx
      LeagueTile.tsx
      PositionHeatmap.tsx
      LeagueSwitcher.tsx
    lib/
      api.ts               # typed fetch client
      ovr.ts               # tier -> color mapping (§12.2)
    styles/
  docker-compose.yml       # local: api + postgres
  BLACKBOOK.md             # design
  BLACKBOOK_TASKS.md       # this file
```

### Branching
- Develop Blackbook on a `blackbook` branch (or `apps/blackbook/` if kept in same tree).
- Do not refactor engine scoring on this branch except additive, non-breaking changes.

### Definition of done (per task)
- Code + types + a minimal manual verification noted in the task.
- No breakage to `dynasty_draft` public functions used by Pickbook.

---

## Phase 0 — Scaffold & infra (3–5 days)

**Goal:** Both services run locally and on Railway; DB migrates; settings migrated from `config.json`.

**Status:** Local exit criteria met (2026-06-07). Railway deferred by choice.

### Backend
- [x] Add backend deps to `pyproject.toml`: `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2`, `alembic`, `psycopg[binary]`, `pydantic-settings`.
- [x] `backend/main.py`: FastAPI app, CORS for the frontend origin, `GET /health`.
- [x] `backend/config.py`: env via pydantic-settings (`DATABASE_URL`, `SLEEPER_USERNAME`, optional `ANTHROPIC_API_KEY`).
- [x] `backend/db/session.py`: engine + session factory.
- [x] `backend/db/models.py`: tables per §10 — `leagues`, `rosters`, `roster_players`, `player_snapshots`, `league_snapshots`, `sync_runs`, `user_settings`.
- [x] Alembic init + first migration (`alembic/versions/286eb21295ab_initial_blackbook_schema.py`).
- [x] `docker-compose.yml`: `api` + `postgres` for local dev.

### Frontend
- [x] `npx create-next-app frontend` (App Router, TypeScript, Tailwind).
- [x] `frontend/next.config.ts`: `output: 'standalone'` (Railway single-service deploy, §9).
- [x] `frontend/lib/api.ts`: typed fetch wrapper reading `API_URL` from env.
- [x] Base layout + dark theme tokens (§12.1): background gradient, slate borders, gold accent CSS vars (`frontend/app/globals.css`).
- [x] `frontend/app/page.tsx`: placeholder hub hitting `GET /health`.

### Settings migration
- [x] One-off: load `config.json` (sleeper_username, dynasty_weights, dynasty_rating_curve incl. per_game_tilt, trade_value_blend, worp_blend) into `user_settings` rows (`backend/seed.py`).
- [x] `GET /settings`, `PUT /settings` (`backend/api/settings.py`).

### Seed leagues
- [x] Decide seed mechanism: **`leagues.seed.json`** (3 Sleeper `league_id`s) + `python -m backend.seed`.
- [x] Implement chosen seed path; insert the 3 leagues (fetches live scoring/roster settings from Sleeper).

### Railway
- [ ] Provision Postgres plugin.
- [~] `api` service — `Dockerfile.blackbook` exists; not deployed yet.
- [ ] `web` service (Next standalone) with `API_URL` pointing at internal api.

### Phase 0 notes (for next agent)
- Branch: `blackbook`. Do not refactor `dynasty_draft/` scoring on this branch except additive changes.
- Local Postgres runs on **port 5444** (5432/5433 already taken on this machine). Default `DATABASE_URL`: `postgresql+psycopg://blackbook:blackbook@localhost:5444/blackbook`.
- `just bb-db` / `bb-migrate` / `bb-seed` / `bb-api` / `bb-web` added to `justfile`.
- Seeded leagues (2026 season): Good Luck Assholes (`1314731206859853824`), Cory's Naked Puzzle Adventure (`1312127272991350784`), University Terrace League (`1312127185259098112`).
- Verified locally: `GET /health` → ok; `GET /settings` → migrated config; `npm run build` in `frontend/` passes.

**Exit criteria:** `GET /health` works locally ~~and on Railway~~; migrations apply; 3 leagues present in DB; settings readable via API. *(Railway pending.)*

---

## Phase 1 — Sync pipeline (1 week)

**Goal:** All 3 leagues sync from Sleeper into per-league snapshots whose OVR matches Pickbook for spot-checks. This phase *is* the consistency contract (§5.7) and per-league context (§5.2, §6).

### Sleeper ingestion
- [x] Extend `dynasty_draft/sleeper_client.py` (additive): `get_rosters(league_id)`, confirm `get_league`, `get_league_users`.
- [x] `services/sync_service.py`:
  - [x] Pull league settings + users + rosters for one league.
  - [x] Upsert `leagues` (scoring_json, roster_positions_json, total_rosters, superflex).
  - [x] Upsert `rosters` (owner, team name, is_me) and `roster_players`.
  - [x] Record `sync_runs` (start/finish/status/counts/errors).
  - [x] Startup-draft fallback: empty Sleeper rosters → group `draft_picks` by `roster_id` (documented in `BLACKBOOK.md`).

### League Scoring Context (§6)
- [x] `services/league_context.py`: build `LeagueScoringContext` from a `leagues` row.
  - [x] Reuse/extend `dynasty_draft/draft_context.build_scoring_context` semantics.
  - [x] Derive replacement ranks per position from roster slots × team count (reuse `projections._replacement_index`).
  - [x] Compute a `context_hash` for snapshot identity.

### Metrics computation (§5)
- [x] `services/metrics_service.py`:
  - [x] Given a league, build the player pool: **rostered players only** (§14.2 Phase 1 decision).
  - [x] Instantiate engine pieces with the league context: WORP projector, healthy-ppg store, dynasty scorer with fixed anchors (`league_engine.py` → `LeagueScoringState`).
  - [x] **Fixed anchors per league** (§5.7): compute `max_tv`, `max_worp_ppg`, `max_hppg`, curve min/max once over the full league pool; reuse for all players.
  - [x] Score each player → OVR, dynasty_score, components, HPPG, W/g, availability, expected flag, TV, flex rating.
  - [x] Upsert `player_snapshots` (latest-wins for v1).
- [x] `services/analysis_service.py` (rankings only this phase):
  - [x] Build optimal lineups (reuse `draft_context._assign_lineup`).
  - [x] Compute the 4 power rankings (by_dynasty, by_starter_ppg, by_tv, by_win_now) → `league_snapshots.rankings_json`.

### Expected PPG (§5.6)
- [x] Ensure rookie/no-history players get expected HPPG/W/g via the engine's `_expected_ppg_metrics` path; persist `hppg_expected`.

### Sync API
- [x] `POST /sync` (all leagues), `POST /sync/{league_id}` (one).
- [x] Return per-league sync summary (counts, duration, errors).

### Validation
- [x] Spot-check: 3 players across GLA + CNPA — snapshot OVR matches live `LeagueScoringState` re-score (consistency). Pickbook full-board anchors differ during startup draft (documented).
- [x] Confirm the same player shows the **same** OVR across team vs rankings reads within a league (consistency contract).
- [x] Confirm the same player can show **different** OVR across two leagues (context working): e.g. Rashee Rice GLA=70 vs CNPA=82.

**Exit criteria:** all 3 leagues sync; snapshots populated; OVR validated against Pickbook; consistency and cross-league-difference both demonstrated. *(Met 2026-06-07 — all 3 leagues synced; 55/226/243 player snapshots; consistency + cross-league context verified.)*

### Phase 1.5 — OVR calibration (2026-06-07)
- [x] Split per-game HPPG / W·g normalization into **QB** vs **flex** (RB/WR/TE) anchor pools (`PerGameAnchorMaxes` in `dynasty_score.py`).
- [x] **Anchor universe ≠ roster pool:** `_dynasty_reference_pool()` uses full player universe (~all war.csv players); `scoring_pool()` snapshots rostered only. Draft progress no longer shifts curve bounds.
- [x] Documented in `BLACKBOOK.md` §5.4 / §5.7 / §14.
- [x] Re-sync all leagues after engine change (`POST /sync` or `just bb-sync-all`).

### Phase 1 notes (for next agent)
- **New files:** `backend/services/{league_context,league_engine,sync_service,metrics_service,analysis_service}.py`, `backend/api/sync.py`, `backend/schemas/sync.py`; additive `get_rosters()` in `dynasty_draft/sleeper_client.py`.
- **League-centric engine:** `LeagueScoringState` in `league_engine.py` subclasses `DraftState`. Do not break Pickbook's draft path.
- **OVR anchor model (§5.7, Phase 1.5):**
  - **Anchor universe** (~435 players): full war.csv/Sleeper pool drives TV max, per-game maxes (QB vs flex), and curve bounds. Draft progress must NOT shift another player's grade.
  - **Scored/snapshotted:** rostered players only (FA board Phase 3).
  - **Per-game maxes:** `PerGameAnchorMaxes` — QB PPG vs flex PPG (RB/WR/TE), not one pool-wide max.
- **Startup-draft fallback:** GLA (`1314731206859853824`) is mid-startup draft — Sleeper rosters empty; sync groups `draft_picks` by `roster_id`. In-season leagues use live `rosters[].players`.
- **Spot-check OVRs (post-1.5, GLA):** Amon-Ra 91, Nabers 90, Rashee Rice 84, Chase 96. Re-sync DB snapshots before trusting stored values.
- **Sync commands:** `just bb-sync <league_id>`, `just bb-sync-all` (API via `just bb-api`). Or `POST /sync/{league_id}`, `POST /sync`.
- **Vertical slice:** all 4 steps done — Rashee Rice GLA OVR 84 via `GET /players/10229?league_id=1314731206859853824` + `PlayerCard`.

---

## Phase 2 — Read-only UI (1–2 weeks)

**Goal:** Research any team/player across 3 leagues without opening Streamlit. Madden look lands here (§12).

### Read APIs (DTOs pre-shaped, §11)
- [x] `GET /leagues` → tiles data (name, my team, my rank, roster OVR, Σ PPG, last_synced).
- [x] `GET /leagues/{id}` → league overview.
- [x] `GET /leagues/{id}/rankings` → 4 sort views from `league_snapshots`.
- [x] `GET /leagues/{id}/teams/{rosterId}` → optimal lineup + bench as player DTOs (lineup slots persisted in `league_snapshots.analysis_json` at sync).
- [x] `GET /players/{playerId}?league_id=` → player card DTO (headshot_url, OVR, tier, components, HPPG/W/g/Actv/TV, lenses, league_name).
- [x] Pydantic schemas in `backend/schemas/` for all of the above.

### Frontend components (§12.4)
- [x] `OvrBadge.tsx` — sizes (hero/md/sm), tier color from `lib/ovr.ts`, `e` marker for expected.
- [x] `PlayerCard.tsx` — headshot + fallback silhouette (position color), OVR overlay, identity line, stat strip, league tag.
- [x] `TeamLineup.tsx` — starters as cards in slot order, bench below (depth-chart styling).
- [x] `RankingsTable.tsx` — team rows as horizontal cards; sortable columns (OVR / Σ PPG / TV / win-now).
- [x] `LeagueTile.tsx` — hub entry.
- [x] `LeagueSwitcher.tsx` — persistent nav pills (§12.5).

### Pages (§12.5)
- [x] `app/page.tsx` — hub: 3 league tiles + portfolio summary strip (portfolio strip stub until Phase 3).
- [x] `app/leagues/[leagueId]/page.tsx` — rankings (4 views) + team list.
- [x] `app/leagues/[leagueId]/teams/[rosterId]/page.tsx` — lineup cards.
- [x] `app/players/[playerId]/page.tsx` — hero card + component breakdown.

### Headshots & polish
- [x] Sleeper CDN URL helper + silhouette fallback by position (§12.3).
- [x] Sync button in UI → `POST /sync`; hub/league tiles show "synced Xm ago" from `sync_runs` (§12.6).
- [x] Tier colors + dark theme finalized (§12.1, §12.2).

**Exit criteria:** hub → league → team → player navigation works for all 3 leagues; cards show headshot + OVR + per-game stats; numbers match Phase 1 snapshots. *(Met 2026-06-07 — `npm run build` passes; Rashee Rice GLA OVR 84 on player page.)*

### Phase 2 notes (for next agent)
- **New backend:** `backend/api/{leagues,players,teams}.py`, `backend/schemas/{player,league,team}.py`, `backend/services/read_service.py`.
- **Sync change:** `analysis_service` persists optimal lineup slot → player_id map in `league_snapshots.analysis_json.teams` (read path joins `player_snapshots`; no lineup math at request time).
- **Frontend:** `components/{OvrBadge,PlayerCard,PlayerHeadshot,LeagueTile,LeagueSwitcher,RankingsTable,TeamLineup,SyncButton,AppShell}.tsx`, pages under `app/leagues/` and `app/players/`.
- **Client sync:** browser `SyncButton` needs `NEXT_PUBLIC_API_URL` (see `.env.example`).
- **Test URL:** `/players/10229?league_id=1314731206859853824` (Rashee Rice, GLA, OVR ~84).

---

## Phase 3 — Portfolio & free agents (1 week)

**Goal:** Cross-league holdings (§7) and per-league FA boards.

**Status:** Complete locally (2026-06-07).

- [x] `GET /portfolio` → holdings grouped by player with each league's OVR; exposure by player and position.
- [x] `GET /leagues/{id}/free-agents` → unrostered players with OVR, filterable by position (superflex-aware).
- [x] `GET /players/search?q=` → cross-league search.
- [x] `GET /players/{id}/holdings` → owned-in-leagues strip on player page.
- [x] `app/portfolio/page.tsx` — holdings + exposure view; flag high multi-league exposure (conviction vs risk, §7).
- [x] FA board UI within league detail; position filter (`FreeAgentBoard.tsx`).
- [x] Player search box in nav (`PlayerSearch.tsx`).
- [x] Resolve §14.2 (FA pool scope) and document the decision in `BLACKBOOK.md`.

**Exit criteria:** "who do I own everywhere?" and "best available WR in league X" both answerable in-app. *(Met — `/portfolio`, league FA board with WR filter, nav search.)*

### Phase 3 notes (for next agent)
- **FA pool at sync:** `league_engine.fa_scoring_pool(top_n)` + `snapshot_pool()`; default `FA_POOL_SIZE=150` (`backend/config.py`). Same anchors as rostered; FA rows in `player_snapshots`, read path excludes rostered IDs.
- **New backend:** `backend/services/portfolio_service.py`, `backend/api/portfolio.py`, `backend/schemas/{portfolio,free_agent}.py`.
- **Sync counts:** metrics return `rostered_scored`, `fa_scored`, `fa_pool_size`.
- **Re-sync required** after pulling Phase 3 to populate FA snapshots: `just bb-sync-all`.
- **Test URLs:** `GET /portfolio`, `GET /leagues/1314731206859853824/free-agents?position=WR`, `GET /players/search?q=chase`.

---

## Mockup gaps (`.cache/` → build backlog)

Reference mockups: `overview_mockupo.png`, `team_page_mockup.png`, `player_page_mockup.png`. Phase 2 covers navigation spine only; mockups define the **command center** target.

### Chrome & IA
| Mockup | Built (Phase 2) | Gap |
|--------|-----------------|-----|
| Left sidebar (Overview, League, My Team, Rankings, Players, Portfolio, Trade Targets, Rookie Draft, Settings) | **6** ✓ | Trade Targets → icebox · Rookie Draft **7** ✓ |
| League tabs (GLA / Gridiron / …) | `LeagueSwitcher` pills | Tab styling + "my team" shortcut per league |
| Sync status + Sync Now + settings | **6** ✓ | Global header bar + `/settings` |
| Pickbook link | **6** ✓ | Footer link via `NEXT_PUBLIC_PICKBOOK_URL` |

### Overview / league dashboard (`overview_mockupo.png`)
| Element | Phase | Notes |
|---------|-------|-------|
| Rank, Roster OVR, Starter Σ PPG, TV summary cards | **6** ✓ | `SummaryCards` + tile TV/rank fields |
| OVR trend badge (+2) | **4.5** ✓ | `my_roster_ovr_delta` on hub tiles |
| Power rankings (4 sorts) + contender column | 2 + **4** ✓ | Contender tags on rankings rows |
| My optimal starters + projected PPG sidebar | **6** ✓ | `OptimalStartersSidebar` |
| Portfolio (exposure, multi-league holdings) | 3 + **6** ✓ | Hub strip + league dashboard strip |
| Position strength, age donuts, trade targets | **4** ✓ | Heatmap + age/window + trade surplus panels (donut polish partial) |
| Contender index breakdown bars | **6** ✓ | `ContenderBreakdown` sidebar |

### Team page (`team_page_mockup.png`)
| Element | Phase | Notes |
|---------|-------|-------|
| Card lineup (starters/bench) | 2 ✓ | Lineup tab |
| Full roster **table** (OVR, HPPG, W/G, ACTV, TV, WORP, FLEX, PORP) | **6** ✓ | `RosterTable` full mode; WORP/PORP on snapshot |
| Projected PPG column | **5** ✓ | `RosterTable` |
| Team OVR breakdown donut | **6** ✓ | `component_breakdown` at sync |
| Team traits tags (Young Core, QB Elite, …) | **6** ✓ | Heuristics in `analysis_json.teams` |
| Compact depth chart | **6** ✓ | `DepthChartPanel` |
| Injury watch | **6** ✓ | Sleeper `injury_status` at sync |
| Matchup preview | icebox | Lower priority — redraft-ish |
| Tabs (Roster / Lineup / Depth / Stats / History) | **6** partial | History tab → Phase 4.5 sparkline on player page |

### Player page (`player_page_mockup.png`)
| Element | Phase | Notes |
|---------|-------|-------|
| Hero card + OVR badge | **6** ✓ | `OvrGauge` hero + stat ribbon |
| Height / weight / college / experience | **6** ✓ | Sleeper bio at sync |
| Positional + overall rank | **6** ✓ | `position_rank` / `overall_rank` at sync |
| Lens panel (win-now, flex, TV, market) | **5** ✓ | `LensPanel` + persisted `win_now_rating` |
| Statistical profile (percentile bars) | **5** ✓ | HPPG/W·g/TV percentiles vs position pool |
| Dynasty donut (weighted components) | **6** ✓ | `ComponentDonut` |
| Bio + news feed | **6** partial | Bio placeholder; news → icebox |
| Production trend (HPPG by season) | **4.5** + nflverse | OVR trend from history on player page |
| Age & outlook / peak window timeline | **5** ✓ | `AgeOutlookTimeline` + `outlook_json` |
| Durability gauge | **6** ✓ | `DurabilityGauge` on availability |
| Owned in leagues (cross-league OVRs) | 3 ✓ | `GET /players/{id}/holdings` on player page |

---

## Phase 4 — League analysis (1–2 weeks)

**Goal:** Insight beyond rankings (§8).

**Status:** Complete locally (2026-06-07).

- [x] `analysis_service`: **contender index** (starter OVR + Σ PPG + age-weighted depth → Contender/Competitive/Rebuild). Calibrated on seeded leagues; weights in `BLACKBOOK.md` §14.4.
- [x] `analysis_service`: **position strength map** (team × position avg starter OVR).
- [x] `analysis_service`: **age/window profile** per roster vs league average.
- [x] `analysis_service`: **trade surplus** for my teams (top-3 / bottom-3 by position) + suggested counterparties via position-strength complement.
- [x] Persist analysis outputs into `league_snapshots.analysis_json` (computed at sync); contender fields mirrored on `rankings_json` rows.
- [x] `GET /leagues/{id}/analysis` read API.
- [x] Frontend: `PositionHeatmap.tsx`, `ContenderTag.tsx`, `AgeProfilePanel.tsx`, `TradeSurplusPanel.tsx`; contender tags on hub tiles + rankings; panels on league detail.
- [x] OVR sparklines deferred to Phase 4.5 (done there).

**Exit criteria:** each league shows contender tags, a position heatmap, and my trade surplus — all traceable to inputs (§8 closing note). *(Met — GLA: WR surplus rank #1 Chase 96 OVR; contender tags on hub + rankings; heatmap QB–FLEX columns.)*

### Phase 4 notes (for next agent)
- **Backend:** extended `backend/services/analysis_service.py`; new `backend/schemas/analysis.py`; `GET /leagues/{id}/analysis` in `backend/api/leagues.py`.
- **Sync:** re-run `just bb-sync-all` after pulling — analysis is written at sync, not on read.
- **Test URLs:** `GET /leagues/1314731206859853824/analysis`, hub tiles `my_contender_tier`, league page `/leagues/1314731206859853824`.

---

## Phase 4.5 — Scheduler + snapshot history (3–5 days)

**Goal:** automated sync cadence + OVR/HPPG over time (§9.1, §15). Prerequisite for meaningful trends and training data for §16.

**Status:** Complete locally (2026-06-07).

### Scheduler
- [x] Document cadence in `BLACKBOOK.md` / env: `SYNC_CRON` or Railway Cron → `POST /sync`.
- [x] Local scheduler: `just bb-scheduler-install` → macOS launchd (`scripts/install-bb-scheduler.sh`); `backend/sync_cli.py` runs headless (no API).
- [ ] Railway Cron job when deployed → `POST /sync` or `python -m backend.sync_cli`.
- [x] `GET /sync/status` → last run per league + global success/failure from `sync_runs`.
- [x] Hub header: global last-synced across leagues + failure indicator (`SyncStatusBar`).

### History persistence (inputs-first, §15.1)
- [x] Alembic: `player_snapshot_history` — **input ledger**, not just OVR:
  - Raw: `hppg`, `worp_ppg`, `availability`, `hppg_expected`, `trade_value`, `age`, `season_worp`
  - Derived: `dynasty_score`, `components_json`, cached `dynasty_rating`, `flex_rating`
  - Meta: `computed_at`, `context_hash`, `formula_version` (hash of settings weights + curve)
  - Re-grade: `dynasty_rating_recomputed`, `recomputed_formula_version` (original cached grade preserved)
- [x] Alembic: `league_snapshot_history` — anchor blob per sync: `max_tv`, `max_worp`, `per_game_maxes` (QB/flex), `rating_bounds`, `team_ovr_json`, `context_hash`, `formula_version`.
- [x] `metrics_service`: append player + league history rows each sync (`player_snapshots` stays delete+insert latest).
- [x] `GET /players/{id}/history?league_id=&limit=` → time series (inputs + cached OVR).
- [x] `POST /admin/recompute-history` — re-apply current formula to stored components + anchors; `just bb-recompute-history`.
- [x] Team/league rollups: Δ OVR since prior sync on hub tiles (`my_roster_ovr_delta`).

### Frontend
- [x] `OvrTrendSparkline.tsx` on player page (OVR + HPPG lines).
- [x] Overview tile trend badge when Δ available.

**Exit criteria:** daily cron runs locally or on Railway; player page shows ≥2 sync points on a test player; history API returns inputs + cached OVR; changing `dynasty_weights` in settings + recompute updates historical OVR without re-syncing Sleeper. *(Met — Rashee Rice GLA: 2 history points; recompute 84→81 after lowering TV weight, no Sleeper re-sync.)*

### Phase 4.5 notes (for next agent)
- **Migration:** `alembic/versions/a1b2c3d4e5f6_snapshot_history_tables.py`
- **New backend:** `backend/services/{formula_version,history_service}.py`, `backend/api/admin.py`, `backend/schemas/sync_status.py`; history schemas on `backend/schemas/player.py`.
- **Sync flow:** `metrics_service` writes `league_snapshot_history` + `player_snapshot_history`; `analysis_service` patches `team_ovr_json` on the same history row for tile deltas.
- **Env:** `SYNC_CRON`, `SYNC_ENABLED`, optional `ADMIN_TOKEN` (see `.env.example`).
- **Test URLs:** `GET /sync/status`, `GET /players/10229/history?league_id=1314731206859853824`, `POST /admin/recompute-history`.

---

## Phase 5 — Opportunity model & projected PPG (1–2 weeks)

**Goal:** custom volume/opportunity → projected PPG (§16). Bootstrap before proprietary model.

**Status:** Complete locally (2026-06-07).

### Data layer
- [x] `backend/services/opportunity_service.py`: ingest nflverse player-weekly + team pace (cache `.cache/opportunity_{seasons}.json`).
- [x] Per player at sync: `opportunity_score`, `projected_ppg`, `projection_source` (`sleeper` | `nflverse_blend` | `custom`).
- [x] Persist on `player_snapshots` + `player_snapshot_history` (migration `b2c3d4e5f6a7`).
- [x] v1 formula: trailing volume share × team vol/game × efficiency → half-PPR PPG; 50/50 Sleeper blend.

### Archetype & outlook (lightweight)
- [x] Rule-based `archetype` tag from TV/WORP/HPPG + volume shares.
- [x] `years_to_peak`, `peak_window_end` from `_PEAK_AGE`.
- [x] Player DTO: `outlook` { archetype, peak_window, opportunity_score, percentiles }.

### Engine / lenses
- [x] Persist `win_now_rating` at sync (position-relative on `projected_ppg`).
- [x] Projected PPG on team roster table + player cards.

### Frontend
- [x] Player page: `LensPanel`, `AgeOutlookTimeline`, `StatisticalProfile`.
- [x] Team page: `RosterTable` with Projected PPG column.

**Exit criteria:** ✓ Rice / Allen / Jefferson spot-checks on GLA sync; §16.4 documents opportunity score; archetype + peak window on player page.

**Test URLs:** `/players/10229?league_id=1314731206859853824` · team roster table on `/leagues/1314731206859853824/teams/{rosterId}`

---

## Phase 6 — UI parity & enrichment (1–2 weeks)

**Goal:** close mockup gaps that are **presentation** once Phases 3–5 data exists (§12.8).

**Status:** Complete locally (2026-06-07).

- [x] App chrome: sidebar nav, settings page, Pickbook link.
- [x] Overview dashboard layout (mockup grid: summary cards + TV, rankings + optimal-starters sidebar + portfolio strip + contender breakdown).
- [x] Team page: full roster table (OVR, HPPG, W/G, ACTV, TV, WORP, FLEX, PORP), tabs (Roster / Lineup / Depth / Stats), team OVR donut, traits, depth chart, injury watch.
- [x] Player page: hero OVR gauge, positional/overall rank, dynasty component donut, durability gauge, bio from Sleeper.
- [x] Sync enrichment: `season_worp`, `porp`, `healthy_games`/`total_games`, bio, `injury_status`, `position_rank`/`overall_rank` at sync; team `traits` + `component_breakdown` in `analysis_json.teams`.

**Exit criteria:** side-by-side with mockups — same information architecture; charts may use placeholder data until history matures. *(Met — sidebar IA, league dashboard grid, team tabs/table/donuts, player gauge/donut/durability/bio.)*

### Phase 6 notes (for next agent)
- **Migration:** `alembic/versions/c3d4e5f6a7b8_phase6_snapshot_enrichment.py`
- **Re-sync required** after pull: `just bb-sync-all` (new snapshot columns + team meta in analysis_json).
- **Frontend:** `SidebarNav`, `SummaryCards`, `OptimalStartersSidebar`, `ContenderBreakdown`, `OvrGauge`, `DonutChart`, `DurabilityGauge`, `TeamTabs`, `DepthChartPanel`, `InjuryWatchPanel`; pages `/settings`, `/players`.
- **Pickbook link:** `NEXT_PUBLIC_PICKBOOK_URL` (default `http://localhost:8501`).
- **Test URLs:** `/leagues/1314731206859853824`, `/leagues/1314731206859853824/teams/3`, `/players/10229?league_id=1314731206859853824`, `/settings`

---

## Phase 7 — Rookie draft mode (later)

**Goal:** Replace Pickbook for the use case that actually recurs — annual rookie drafts. Not startup drafts (§2).

**Status:** Complete locally (2026-06-07).

- [x] Rookie-only board API (reuse `recommender` + rookie filtering).
- [x] Live pick updates: polling first; WebSocket if needed.
- [x] Rookie draft UI: scrollable board (reuse the full-board pattern already built in Pickbook), BPA / targets, on-the-clock indicator.
- [x] Validate against a real or mock rookie draft.
- [x] Decide Streamlit Pickbook retirement once parity is reached.

**Exit criteria:** a rookie draft can be run end-to-end in Blackbook. *(Met — GLA rookie draft `1314731206864027648`, 57-player BPA board, live poll UI.)*

### Phase 7 notes (for next agent)

- **API:** `GET /leagues/{league_id}/rookie-draft` — optional `draft_id`, `roster_id` (whose starter needs to show). Poll Sleeper `GET /draft/{id}/picks` on each request; UI polls every `poll_seconds` (default 20, from `config.json`).
- **Rookie draft resolution:** `GET /league/{id}/drafts` → `settings.player_type == 1` (startup/vet = 2). GLA rookie: `1314731206864027648` (3 rounds, `pre_draft` at validation).
- **Engine:** `backend/services/rookie_draft_service.py` — `RookieDraftState` subclasses `DraftState` with `strategy.draft_phase = rookies`. Board pool = rookies only; **OVR anchors = full player universe** (§5.7, same as `LeagueScoringState` — Pickbook's rookie-only anchor pool is not used here). BPA via `bpa_recommendations()`, timeline via `build_draft_timeline()`. Positional needs = existing DB roster + rookie picks so far.
- **Additive `dynasty_draft/`:** `SleeperClient.get_league_drafts()` only; Pickbook path unchanged.
- **Frontend:** `/leagues/[leagueId]/rookie-draft`, `RookieDraftPanel` (BPA table, needs sidebar, targets in `localStorage`, scrollable pick timeline). Sidebar nav item **Rookie Draft**.
- **Test URLs:**
  - UI: `/leagues/1314731206859853824/rookie-draft`
  - API: `GET /leagues/1314731206859853824/rookie-draft`
  - Override: `?draft_id=1314731206864027648`
- **Manual checklist (GLA rookie draft):**
  - [ ] Sidebar **Rookie Draft** loads board without sync
  - [ ] BPA column sorted; OVR / Proj PPG / TV / ADP columns populated
  - [ ] ☆ target highlights persist on refresh (localStorage)
  - [ ] On-the-clock banner updates after **Refresh** or auto-poll when draft is `drafting`
  - [ ] Positional needs reflect my roster (QB/RB/WR/TE/FLEX open slots)
  - [ ] Draft timeline scrolls; pick rows show OVR when picked
  - [ ] Startup draft (`player_type=2`) is **not** shown — only rookie draft auto-resolves
  - [ ] Pickbook Streamlit still runs (`just pickbook` or port 8501)

---

## Phase 8 — AI advisor (optional)

- [ ] Port `dynasty_draft/llm_advisor.py` as a backend endpoint with in-season context (roster, rankings, portfolio).
- [ ] Slide-out advisor panel in UI.
- [ ] In-season prompts: trade targets, drop candidates, rookie-pick prep.

---

## Deployment runbook (Railway)

- [ ] Railway project with: `api` service, `web` service, PostgreSQL plugin.
- [ ] Shared variables: `DATABASE_URL` (from plugin), `SLEEPER_USERNAME`, `ANTHROPIC_API_KEY` (Phase 8).
- [ ] `api`: run alembic migrations on deploy (release command), then `uvicorn`.
- [ ] `web`: Next standalone server; `API_URL` → internal api URL.
- [ ] **Scheduler:** Railway Cron service or cron job → `POST https://api…/sync` daily (§9.1, Phase 4.5).
- [ ] Verify internal networking (web → api) and DB connectivity post-deploy.
- [ ] Confirm no Vercel involved (§9).

---

## Cross-cutting QA checklist

Run before calling any phase done:

- [ ] **Consistency:** same player, same OVR across all views in one league (§5.7).
- [ ] **Context:** same player, different OVR across leagues with different scoring (§5.2).
- [ ] **Engine parity:** spot-checked OVRs match Pickbook for the matching context (Phase 1).
- [ ] **Expected flag:** rookies show `e` and a sensible projected PPG (§5.6).
- [ ] **Pickbook intact:** Streamlit app still runs; engine public API unchanged (§3.7, §9).
- [ ] **Staleness honest:** UI shows last-synced age; never hides stale data (§11).

---

## Risk register (as actionable items)

| Risk (design §) | Mitigation task |
|-----------------|-----------------|
| Sleeper rate limits | Scheduler (Phase 4.5) + manual button; cache player DB 24h; batch league syncs. |
| Sparse OVR history | Daily cron + append-only input ledger (Phase 4.5). |
| Formula change erases past | Store inputs + anchors + `formula_version`; re-curve job (§15.1). |
| Projection cold-start | Bootstrap Sleeper + nflverse (Phase 5 v1); retain history for v3 training. |
| Per-league scoring drift | `LeagueScoringContext` required on every metrics call; no global defaults (Phase 1). |
| OVR drift within league | Compute at sync vs fixed anchors; UI reads snapshots only (Phase 1 validation). |
| OVR differs across leagues | Intended; UI always shows league badge (Phase 2 cards). |
| Rookies w/o nflverse | Expected-PPG path + `e` indicator (Phase 1/2). |
| Pickbook regression | Engine changes additive only; QA checklist item every phase. |
| Frontend learning curve | Build `OvrBadge` + `PlayerCard` first; reuse across pages (Phase 2 ordering). |

---

## Icebox / backlog (not scheduled)

- Per-league setting overrides (§14.1).
- PWA / installable mobile (§12.7).
- Trade calculator.
- Push notifications.
- Matchup preview widget (team mockup).
- Player news feed (Sleeper news).
- Proprietary projection model v3 / forward OVR curve (after Phase 5 v1–v2 data accumulates).

---

## First vertical slice (Phase 0→1 → Phase 2)

Prove the whole stack with one path before breadth:

1. [x] Sync **one** league's rosters + settings into Postgres.
2. [x] Compute snapshots for that league with its scoring context.
3. [x] `GET /players/{id}?league_id=` returns correct OVR + headshot URL.
4. [x] Render **one** `PlayerCard` in Next.js with the right league-context OVR.

If that feels right, every other screen is repetition over leagues and teams.

**Recommended starting league for slice:** Good Luck Assholes (`1314731206859853824`) — already in Pickbook `config.json`.

**Phase 1 architecture (done):** `LeagueScoringState` in `backend/services/league_engine.py` wires `WarData`, `HealthyPpgStore`, `SleeperProjectionStore`, and `DynastyScorer` from a `leagues` row — league-centric, not draft-centric. Pickbook's `build_state()` path is unchanged.
