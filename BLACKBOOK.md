# Dynasty Blackbook — Design & Intent

This is the **design book**: what Blackbook is, the concepts it models, the principles it holds, and *why* it works the way it does. It is the durable reference. The executable plan lives in `BLACKBOOK_TASKS.md`.

When a task or implementation decision conflicts with this document, this document wins — or this document gets updated deliberately. Code should be explainable by pointing at a section here.

---

## 1. Purpose & intent

Blackbook is a **personal dynasty research hub** spanning the three Sleeper dynasty leagues I play in. It is an **in-season analysis tool**, not a draft app. Its job is to let me answer questions like:

- How good is my roster in *this* league, really — not by market hype but by production and dynasty value?
- Who are the contenders, who is rebuilding, and where are the soft spots I can attack?
- Which players do I own across multiple leagues, and where am I over-exposed?
- If I look at any player, what is their dynasty grade *in the context of this specific league's scoring and roster rules*?

The Pickbook Streamlit app already proved the **scoring engine** (dynasty OVR, snap-filtered per-game production, projections, lineup optimization, league rankings). Blackbook keeps that engine as a library and replaces the presentation layer with a real frontend that *looks* like a franchise-mode front office: player headshots, a prominent OVR, and league-level analysis.

**Intent in one line:** make dynasty roster research feel like opening a Madden franchise screen, backed by honest, context-aware grades.

---

## 2. Who it's for & how it's used

**User:** me, one person, three leagues. No multi-tenant concerns, no public users.

**Primary mode:** in-season, asynchronous research — evaluating my teams, scouting opponents, planning trades, prepping for rookie drafts.

**Explicitly not the primary mode:** live startup drafts. I will rarely do startup drafts. Pickbook (Streamlit) remains the draft-night tool. Blackbook will eventually gain a **rookie draft** mode because rookie drafts happen every year and matter.

**Cadence:** I open it a few times a week, sometimes daily during trade season or before rookie drafts. Data freshness of minutes-to-hours is fine. Real-time is only relevant for the future rookie-draft feature.

---

## 3. Design principles (non-negotiables)

1. **OVR is the protagonist.** Every player surface leads with a single, legible 50–99 grade. If a screen doesn't make the grade obvious, it's wrong.

2. **Grades are honest, not market echoes.** Trade value (the market) is *one input*, not the answer. Production (snap-filtered per-game), projection, age, and dynasty trajectory all matter. The tool should sometimes disagree with consensus — that's the point.

3. **Context changes the grade.** A player's OVR is **league-relative**. The same player can and should grade differently across leagues with different scoring, roster construction, and league size. This is a feature, never a bug.

4. **Consistency within a league is sacred.** Within a single league's snapshot, a player's OVR is identical everywhere it appears. No view recomputes against a different sub-pool. (This is the lesson from the Rashee Rice cross-tab bug.)

5. **Snapshots, not live math.** Grades are computed at sync time against fixed, league-wide anchors and stored. The UI reads snapshots. This guarantees principle 4 and keeps the frontend dumb and fast.

6. **The engine is a library.** All scoring lives in `dynasty_draft/` (the core). The backend orchestrates and stores; the frontend renders. Scoring logic never leaks into API handlers or React components.

7. **Reuse over rebuild.** Pickbook's engine is the asset. Blackbook is a new shell around it, not a rewrite of the math.

8. **Personal-scale pragmatism.** No premature scale engineering, no auth complexity, no second hosting platform. Railway + Postgres is enough. Optimize for my iteration speed.

---

## 4. Core concepts & domain language

A shared glossary so the design, API, DB, and UI all use the same words.

| Term | Meaning |
|------|---------|
| **League** | One Sleeper dynasty league I'm in. Carries its own scoring + roster rules. |
| **Scoring Context** | The full set of league rules that affect grades: PPR, TE premium, pass-TD points, bonuses, roster slots, superflex, league size. The lens through which every metric is computed. |
| **OVR / Dynasty Rating** | The headline 50–99 grade. League-relative dynasty value. |
| **Dynasty Score** | The raw 0–1 composite before the display curve. Used for precise ordering. |
| **Components** | The normalized 0–1 breakdown that produces the score: trade value, WORP (production), upside, age, trajectory. |
| **TV (Trade Value)** | Blended market value (dynasty-daddy + KTC). The market's opinion. |
| **WORP** | Wins Over Replacement Player — production value vs a league-specific replacement baseline. |
| **HPPG** | Healthy Points Per Game — half-PPR points averaged over weeks the player was actually active (snap-filtered). |
| **W/g** | WORP per game — per-week value over replacement, the per-game production signal. |
| **Actv (Availability)** | Healthy weeks / total weeks. Durability signal. |
| **Expected PPG** | Projected per-game production for players without nflverse history (rookies). Flagged as expected. |
| **Flex Rating** | RB/WR/TE graded on one shared 50–99 scale for cross-position flex decisions. |
| **Snapshot** | A point-in-time, league-scoped computation of player grades and league rankings, persisted to the DB. |
| **Portfolio** | My holdings viewed across all leagues at once. |

---

## 5. The OVR system (the centerpiece)

This is the most important section in the book. OVR is the product. Everything else frames it.

### 5.1 What OVR represents

OVR is a **dynasty value grade on a 50–99 scale**, Madden-style. It answers: *how valuable is this player to own, long-term, in this league?* It blends market value, real production, youth, and developmental trajectory into one number, then stretches it onto a curve so elites land in the mid-to-high 90s and the replacement-level mass sits in the 50s–60s.

OVR is **not** pure win-now value and **not** pure trade value. Those exist as separate lenses (§5.8). OVR is the dynasty headline.

### 5.2 Why OVR is league-relative (the core design commitment)

The same player is worth different amounts in different leagues. A pass-catching back is worth more in 1.0 PPR than 0.5. A QB is worth dramatically more in superflex than single-QB. A WR4 is a starter in a 12-team 3-WR league and a bench piece in a shallow league. Replacement level — the baseline OVR is measured against — moves with league size and roster slots.

Therefore **OVR must be computed inside a Scoring Context**, never against global defaults. The Scoring Context determines:

- **Half-PPR vs PPR vs standard** → which fantasy-point total feeds HPPG.
- **TE premium, pass-TD points, long-TD bonuses** → scoring weights.
- **Roster slots (QB/RB/WR/TE/FLEX/SUPER_FLEX counts) × league size** → replacement rank per position (VOR baseline).
- **Superflex flag** → QB replacement depth and value.

Two leagues, two contexts, two legitimately different OVRs for the same player. The UI always shows which league an OVR belongs to.

### 5.3 The composite formula

OVR derives from a weighted 0–1 composite (current engine defaults; tunable in settings):

| Component | Weight | Meaning |
|-----------|-------:|---------|
| **Trade value** | 45% | Market dynasty capital (dynasty-daddy ⊕ KTC blend), normalized to the league's top player. |
| **WORP / production** | 25% | Value over replacement — but **blended with per-game production** (see §5.4). |
| **Upside / ceiling** | 15% | Spike-week / breakout potential. |
| **Age** | 10% | Youth premium relative to positional peak age. |
| **Trajectory** | 5% | Market-ahead-of-production signal for young players (development bets). |

The composite is then stretched onto 50–99 via a **power curve** (exponent ≈ 0.54) against the league's full-pool min/max, so the distribution feels like Madden ratings rather than a flat percentile.

**Age premium** uses positional peak ages (QB 29, RB 25, WR 27, TE 26): players years-from-peak get the full youth bonus, players past peak taper down. This is what keeps a 24-year-old ahead of a same-production 30-year-old in dynasty.

**Trajectory** captures the "the market believes before the box score does" pattern (young player, high TV, thin production) — a small nudge so true breakout-profile players aren't buried by lack of history.

### 5.4 Production = per-game, not season totals (the per-game tilt)

A season WORP total punishes players who missed time and rewards compilers. For dynasty *talent* evaluation, the question is "how good are they **when they play**?" So the WORP component is **blended toward per-game production**:

- **HPPG** — half-PPR points averaged only over **healthy weeks** (snap-filtered: ≥15% offensive snaps or ≥8 snaps; QBs by pass attempts).
- **W/g** — per-game value over a league-specific replacement per-game baseline, calibrated to the WORP scale.
- The two are combined (≈55% W/g, 45% HPPG), lightly **discounted by availability** (durability still matters — a player who produces but is never healthy is worth less).

A configurable **per-game tilt** (default 0.65) sets how much the season-WORP component is replaced by this per-game signal. Tilt 0 = pure season value; tilt 1 = pure per-game. This lets me lean win-now (high tilt) or dynasty-market (low tilt) globally.

**Flex vs QB per-game anchors (Phase 1.5):** HPPG and W/g normalize against **role-appropriate ceilings**, not one pool-wide max:

| Group | Positions | Anchor pool | Why |
|-------|-----------|-------------|-----|
| **Flex PPG** | RB, WR, TE | Max HPPG / W·g among flex-eligible players in the league pool | A WR at 16 PPG is elite skill production — not compared to Josh Allen's 23 QB PPG |
| **QB PPG** | QB | Max among QBs only | Passing TD volume is a different scale |

Fixed once per sync from the league player pool (§5.7). This is separate from **flex rating** (§5.8) — flex rating ranks RB/WR/TE head-to-head for lineup decisions; flex PPG anchors feed the dynasty OVR production component.

### 5.5 Replacement level & VOR — per league

WORP and W/g are meaningless without a **replacement baseline**, and that baseline is league-specific. It's derived from roster slots × league size:

- QB replacement depth grows in superflex.
- RB/WR/TE replacement ranks fold in a share of FLEX slots.
- The baseline is the per-game (or season) production of the *N*-th ranked player at that position, where *N* is the number of leaguewide startable spots.

VOR = player production − replacement production. WORP = VOR × a position-specific calibration factor fit against the dynasty-daddy WORP scale. **All of this is recomputed per league**, because the replacement player is different in each.

### 5.6 Expected production for rookies / no-history players

Players without nflverse weekly history (rookies, deep stashes) still need an HPPG/W/g so they aren't blank or unfairly zeroed:

1. **Preferred:** Sleeper season projection ÷ 17 → expected PPG; projected WORP ÷ 17 → expected W/g.
2. **Fallback:** impute from trade value / blended WORP using the league's replacement baseline and calibration.

These are flagged `expected` (UI shows a small `e`) so I always know which numbers are real vs projected. Expected players are treated at full availability (17/17) since there's no injury history yet.

### 5.7 The consistency contract

This is a hard guarantee, learned from a real bug where per-game normalization used the current view's sub-pool and the same player showed different OVRs on different tabs.

| Scope | Guarantee |
|-------|-----------|
| **Within a league snapshot** | A player's OVR is identical on every screen (team, rankings, player card, FA board) until the next sync. |
| **Across leagues** | OVR may differ. Always labeled with the league. |
| **Anchors** | Per-game maxes (`max_worp_ppg`, `max_hppg`) split **QB vs flex**, TV max, and curve min/max are **fixed from the full player universe** for that league's scoring context — never from who happens to be rostered or how far a startup draft has progressed. |
| **Who gets scored** | Snapshots are written for **rostered players + top-N FAs** (§14.2). Anchors are universe-wide; roster membership only affects who gets a row, not another player's grade. |
| **Persistence** | OVR + components are stored on the snapshot. The UI never recomputes; it reads. |

### 5.8 OVR lenses (one headline, multiple readings)

OVR is the dynasty headline, but the engine already produces complementary grades. Blackbook surfaces them as **lenses on the same player**, not competing numbers:

- **Dynasty OVR** — the default headline (long-term value, age-aware).
- **Win-now** — starter WORP + projection emphasis; "help me this year."
- **Flex rating** — RB/WR/TE on one 50–99 scale for lineup/flex decisions.
- **TV (market)** — what the player would fetch in a trade.

Design intent: a player card shows **OVR big**, with the other lenses available as secondary stats or a small toggle — so I can see "great dynasty asset, mediocre win-now" at a glance.

---

## 6. League Scoring Context (the lens, modeled)

The Scoring Context is a first-class object, built from Sleeper league settings at sync time and carried into every metric call. Conceptually:

```
LeagueScoringContext
  ppr                 # 1.0 / 0.5 / 0.0
  te_premium          # bonus per TE reception
  pass_td_points      # usually 4 or 6
  long_td_bonuses     # 40+ yard pass/rec/rush bonuses
  roster_positions    # [QB, RB, RB, WR, WR, TE, FLEX, SUPER_FLEX, BN, ...]
  team_count          # number of rosters
  superflex           # derived from roster slots / scoring type
  → derived: replacement_rank[pos], worp_per_vor[pos], rating_anchors
```

**Design rules:**
- Nothing computes a grade without a context. There is no "default league."
- The context is derived from Sleeper truth (`scoring_settings`, `roster_positions`, `total_rosters`), with documented fallbacks only when Sleeper omits a field.
- The context is part of the snapshot's identity: a snapshot is *(league, computed_at, context_hash)*. If league settings change, grades are expected to move.

---

## 7. Cross-league portfolio (concepts)

Owning the same players across leagues is a real dynasty consideration (correlated risk, conviction signal). Blackbook models my holdings as a **portfolio**:

- **Holdings** — every player I roster, in which leagues, with each league's OVR for that player (which may differ).
- **Exposure** — concentration by player and by position across leagues ("I'm 3-for-3 on Chase," "I'm RB-light everywhere").
- **Conviction vs risk** — high multi-league exposure to a young stud is conviction; high exposure to an aging or injury-prone player is risk worth flagging.
- **Open targets** — players I own *nowhere* who grade well and are available in at least one league.

Portfolio is a cross-cutting view built *on top of* per-league snapshots; it never invents a "global OVR." It shows each league's grade side by side.

**API (Phase 3):** `GET /portfolio` (holdings + exposure), `GET /leagues/{id}/free-agents?position=` (unrostered snapshot reads), `GET /players/search?q=` (cross-league name search), `GET /players/{id}/holdings` (owned-in-leagues on player page).

---

## 8. League analysis (designed heuristics)

Beyond per-team rankings, Blackbook should produce *insight*. Each analysis is a deliberate heuristic, documented so I trust the output.

### 8.1 Power rankings (already in engine)
Teams ranked four ways, all from optimal-lineup assignment:
- **By dynasty OVR** — average roster OVR (long-term).
- **By starter Σ PPG** — sum of optimal starters' HPPG/expected PPG (weekly scoring power).
- **By trade value** — total market capital.
- **By win-now** — starter WORP + projection.

These are not the same ranking, and the gaps between them are themselves insight (high TV + low PPG = overvalued market darlings).

### 8.2 Contender index
A single classification — **Contender / Competitive / Rebuild** — from a weighted blend of:
- Optimal-starter OVR (can they field a strong lineup now?),
- Starter Σ PPG (weekly ceiling),
- **Age-weighted depth** (is the core young enough to sustain, or is the window closing?).

Intent: tell me at a glance who's pushing now vs who's selling, so I know who to trade with.

**Implemented (Phase 4):** computed at sync in `analysis_service`, persisted in `league_snapshots.analysis_json.contender_index` and mirrored on each rankings row (`contender_tier`, `contender_rank`, `contender_score`). Weights and tier cutoffs are fixed in §14.4. UI shows tags on hub tiles and power rankings; inputs are exposed on `GET /leagues/{id}/analysis`.

### 8.3 Position strength map
Per league, a heatmap of **average starter OVR by team × position**. Reveals where each roster is strong/weak — the basis for trade fits ("they're QB-rich, RB-poor; I'm the opposite").

**Implemented:** `analysis_json.position_strength` — columns follow starter slots (QB, RB, WR, TE, FLEX; SUPER_FLEX rolls into FLEX). Multiple RB/WR slots are averaged per position group. `PositionHeatmap.tsx` on league detail.

### 8.4 Age & window profile
Per roster: age distribution of starters vs league average, and a "competitive window" read (young core trending up vs aging core trending down).

**Implemented:** `analysis_json.age_profiles` — OVR-weighted starter avg age vs league avg; window label **rising** (≥1 yr younger), **peak** (within 1 yr), **closing** (≥1 yr older). My-team panel on league detail lists optimal starters with ages.

### 8.5 Trade surplus
For my teams: positions where I rank **top-3** (surplus to sell) or **bottom-3** (need to buy) in the league. Combined with §8.3 to suggest realistic counterparties.

**Implemented:** `analysis_json.trade_surplus` for `is_me` roster — surplus/needs from position-strength ranks; counterparties are top-3 / bottom-3 complements per position. Trade Surplus panel on league detail.

> Analyses are presented with their inputs visible. No black-box "trust me" numbers — every grade and tag can be traced to its components.

---

## 9. System architecture & rationale

```
frontend (Next.js + Tailwind)   ── renders cards, hubs, rankings; reads snapshots via REST
        │  REST JSON
backend (FastAPI)               ── sync orchestration, persistence, read APIs
        │  imports as library
dynasty_draft/ (engine)         ── OVR, per-game metrics, projections, lineups, rankings
        │
PostgreSQL  ·  Sleeper API  ·  war.csv + nflverse cache
```

**Why a Python API instead of putting logic in the frontend:** the scoring engine is Python and stays Python. The frontend should never reimplement lineup assignment or OVR math. The API hands over fully-shaped DTOs.

**Why Postgres:** three leagues, persisted snapshots, settings, and (later) history. Snapshots are the mechanism that enforces the consistency contract (§5.7) and keep the UI fast.

**Why Railway-only (no Vercel):** one project, one bill, internal networking between API and DB, shared env vars. Next.js runs as a second Railway service with standalone output. A second platform would add deploy, env-sync, and CORS complexity for no benefit at personal scale.

**Why keep Pickbook (Streamlit) alive:** it's the working draft tool. Blackbook imports the same engine as a library and does not modify scoring in breaking ways, so both can coexist until rookie-draft mode makes Streamlit redundant.

### 9.1 Sync scheduler

OVR-over-time and honest staleness both require **regular syncs**, not just manual button clicks. The API stays stateless: something external triggers `POST /sync` on a cadence.

| Piece | Intent |
|-------|--------|
| **Trigger** | Railway Cron, local `cron`, or GitHub Actions → `POST /sync` (or per-league). No in-process scheduler in the API process (avoids duplicate runs on redeploy / multi-instance). |
| **Cadence** | In-season default: **daily** (`SYNC_CRON=0 6 * * *` in env). Trade season / weekly lineup churn: **2×/day**. Off-season / rookie-draft prep: **daily** + manual. `SYNC_ENABLED` documents intent; cron is external. |
| **Observability** | `sync_runs` is the audit log. `GET /sync/status` exposes global last success/failure + per-league status. Hub header (`SyncStatusBar`) shows last sync age and failure state. |
| **History dependency** | Scheduler is a **prerequisite** for meaningful OVR trend charts — without cadence, history is sparse noise. |

Manual sync remains forever (draft night, "I just traded, refresh now"). **Local scheduler:** `just bb-scheduler-install` registers a macOS launchd job that runs `scripts/bb-sync-cron.sh` daily (hour/minute from `SYNC_CRON`); uses `python -m backend.sync_cli` so the API does not need to be running. Railway Cron deferred with deploy.

---

## 10. Data model design (intent)

The schema exists to serve the consistency contract and the cross-league portfolio. Design intent matters more than exact DDL (that lives in tasks).

- **`leagues`** — identity + the raw Sleeper scoring/roster settings that define the Scoring Context. Source of truth for "what lens applies."
- **`rosters` / `roster_players`** — who owns whom, per league, from Sleeper. The portfolio is built from this.
- **`player_snapshots`** — the heart: per *(league, player)* computed grade — OVR, dynasty score, components, HPPG, W/g, availability, expected flag, TV, flex. **This is what the UI reads.** Latest-wins for current truth.
- **`player_snapshot_history`** *(§15, Phase 4.5)* — append-only **input ledger** per sync: raw + normalized metrics that fed OVR, cached `dynasty_rating`, `formula_version`, and optional `dynasty_rating_recomputed` when formula changes. Powers trends and **retroactive re-grade**.
- **`league_snapshot_history`** *(§15, Phase 4.5)* — league-level anchor state per sync (`context_hash`, `rating_bounds`, per-game maxes QB/flex, TV/WORP maxes, `team_ovr_json`) so historical OVR can be recomputed in context.
- **`league_snapshots`** — per-league precomputed rankings (the four power-ranking views + analysis outputs) so the hub is a single fast read. Team optimal-lineup slot assignments (player IDs only) live in `analysis_json.teams` so team pages are snapshot reads without re-running lineup math.
- **`sync_runs`** — observability: when, status, errors, counts. So I can see "synced 6m ago" and debug failures.
- **`user_settings`** — my global knobs (dynasty weights, per-game tilt, TV blend, Sleeper username), migrated out of `config.json`. Possibly per-league overrides later.

**Key intent:** a snapshot is immutable truth for a moment in time. Reads are cheap; writes happen only at sync. The same-OVR-everywhere guarantee is a *storage* guarantee, not a runtime hope.

---

## 11. API design philosophy

- **DTOs are pre-shaped for rendering.** The frontend should not compute lineups, sort rankings, or derive OVR tiers. If the UI needs it, the API provides it.
- **League context is explicit.** Any player grade is requested and returned *with* its `league_id` and `league_name`. There is no contextless player grade endpoint.
- **Player payloads always carry the headshot URL and the OVR tier** so the frontend stays declarative.
- **Reads are snapshot reads.** Read endpoints never trigger computation; `POST /sync` is the only thing that computes.
- **Errors are honest.** Stale data is labeled with its age, not hidden.

(Concrete endpoint list and payload schemas live in `BLACKBOOK_TASKS.md`.)

---

## 12. UI / UX design language (Madden-inspired)

The feeling target: opening a **franchise-mode front office**. Dark, premium, numbers-forward, with the OVR as the hero of every card. Not literal Madden assets — the *energy* of rated player cards and depth charts.

### 12.1 Visual identity
- **Mood:** dark, focused, "war room." Deep charcoal/navy base (`#0f1419` → `#1a2332` gradient), subtle grid/noise texture.
- **Accent:** gold for elite tiers and highlights; restrained elsewhere.
- **Surfaces:** rounded cards with slate borders and soft elevation; hover lift for interactivity.

### 12.2 OVR badge (the signature element)
- A **circular or shield badge** showing the 50–99 number, large and bold (condensed, near-black weight).
- **Tier color** drives the badge fill/ring:
  - **90–99 Elite** — gold
  - **80–89 Blue-chip** — blue
  - **70–79 Solid** — green
  - **60–69 Depth** — slate
  - **50–59 Replacement** — muted gray
- Rookies / expected grades carry a subtle `e` marker.
- The badge is reused at multiple sizes: hero (player page), medium (cards), small (table rows).

### 12.3 Player card
- **Headshot** left (Sleeper CDN: `https://sleepercdn.com/content/nfl/players/thumb/{player_id}.jpg`), with a **position-colored silhouette fallback** (QB gold, RB green, WR blue, TE orange).
- **OVR badge** overlaid top-right.
- **Identity line:** name, position pill, NFL team, age.
- **Stat strip:** HPPG · W/g · Actv · TV, with the expected `e` flag when relevant.
- **League tag:** which league's grade this is (always present when ambiguous).
- **Secondary lenses:** win-now / flex / market available as smaller stats or a toggle.

### 12.4 Component vocabulary
- **OvrBadge** — the rating chip, tier-colored, sized by context.
- **PlayerCard** — headshot + OVR + identity + stats. The atom of the whole app.
- **TeamLineup / Depth chart** — optimal starters as cards in slot order, bench below, styled like a franchise depth chart.
- **PowerRankings / standings** — team rows as horizontal "team cards": rank badge, team name, roster OVR, starter Σ PPG, TV; sortable columns.
- **LeagueTile** — hub entry per league: name, my team, my rank, roster OVR, Σ PPG, last synced.
- **PositionHeatmap** — team × position grid, cell color = avg starter OVR.

### 12.5 Information architecture
- **Hub (home):** three league tiles + a portfolio summary strip.
- **League detail:** power rankings (4 sort views) → team drill-downs → position heatmap / analysis.
- **Player page:** hero card + cross-league ownership + component breakdown.
- **Portfolio:** holdings and exposure across all leagues.
- **Top nav:** persistent **league switcher** as pills — I should never be unsure which league context I'm reading.

### 12.6 Motion & feedback
- Subtle card hover lift and OVR badge sheen for elites.
- Sync action shows progress and resolves to a "synced Xm ago" indicator.
- Sorting/filtering is instant (client-side over snapshot data).

### 12.7 Responsive intent
- Desktop-first for research depth, but readable on phone (I'll glance at it on mobile). No native app; responsive web is enough. PWA is a possible later nicety, not a v1 goal.

### 12.8 UI mockup targets (`.cache/` reference)

High-fidelity mockups (`overview_mockupo.png`, `team_page_mockup.png`, `player_page_mockup.png`) define the **north star** beyond Phase 2. Gap summary vs current build — see `BLACKBOOK_TASKS.md` §Mockup gaps.

**Shared chrome (all pages):** left sidebar nav (Overview, League, My Team, Rankings, Players, Portfolio, …), league switcher tabs, sync status + Sync Now, settings gear. Phase 2 has top pills only.

**Overview / league dashboard:** contender index, power rankings with sort tabs, my optimal starters sidebar (with projected PPG), portfolio strip, position strength, age donuts, trade targets. Phase 2 hub is league tiles + portfolio stub.

**Team page:** full roster **table** (OVR, HPPG, W/G, ACTV, TV, WORP, FLEX, PORP), team traits, depth chart, injury watch, matchup preview, OVR trend badge (+2). Phase 2 is card-based lineup only.

**Player page:** hero OVR gauge + positional/overall rank, lens panel (win-now, flex, TV), statistical profile percentiles, dynasty donut, bio/news, production trend chart, age/outlook timeline with peak window, durability gauge, cross-league ownership. Phase 2 is hero card + component bars.

Build order: ship data foundations (history, lenses, portfolio) before visual polish that depends on them.

---

## 13. Non-goals (v1)

- Live **startup** draft UX (stays on Streamlit Pickbook).
- Multi-user / auth (personal tool; a single API key on Railway if anything).
- Trade calculator, push notifications, native mobile app.
- A "global" cross-league OVR (grades are league-relative by design; portfolio shows them side by side).
- Proprietary projection model in v1 (bootstrap with Sleeper + nflverse; custom model is a later phase).
- In-app scheduler UI (cron/Railway config is enough; UI only needs last-synced + manual trigger).

---

## 14. Open design questions

To resolve as the build progresses; capture decisions back into this book.

1. **Per-league setting overrides** — do dynasty weights / per-game tilt stay global, or do some leagues warrant their own knobs (e.g. a TE-premium league)?
2. **FA pool scope** — **Resolved (Phase 3, 2026-06-07):** OVR **anchors** still come from the full player universe (unchanged). At sync, `player_snapshots` are written for **rostered players + top-N unrostered by blended trade value** (default N=150, `FA_POOL_SIZE` env). FA grades use the same fixed anchors as rostered players, so a player's OVR is identical on team, rankings, player card, and FA board until the next sync (§5.7). The FA board read path filters snapshots to players not on any roster — no request-time scoring. Rankings/lineups still join only rostered players. N is tunable if sync time grows; deep waiver wire beyond N is out of scope for v1.
3. **Lens prominence** — is win-now a toggle on the player card, or a persistent secondary number? Depends on how often I think win-now vs dynasty.
4. **Contender index thresholds** — **Resolved (Phase 4, 2026-06-07):** weights and tier cutoffs documented in §14.4; calibrated against seeded 10-team leagues.
5. **Sync trigger** — **Direction (2026-06-07):** manual + external scheduler (§9.1). Daily in-season default; 2×/day during trade season. API exposes `POST /sync`; Railway Cron or local cron is the runner.
6. **Snapshot history** — **Resolved (Phase 4.5):** append-only `player_snapshot_history` + `league_snapshot_history` at each sync; store **OVR inputs**, not just the headline grade (§15). `player_snapshots` stays latest. Re-grade via `POST /admin/recompute-history`.
7. **Projected PPG / opportunity** — **Direction (2026-06-07):** build a **custom** opportunity model (not outsource the answer to Sleeper alone). Bootstrap with Sleeper projections + nflverse volume; evolve toward offense context + role share → projected PPG. See §15.

### 14.4 Contender index calibration (Phase 4)

Composite score (0–100) blends three league-normalized inputs (min–max within the league; flat field → 50 for all):

| Input | Weight | Source |
|-------|--------|--------|
| Starter avg OVR | **40%** | `starter_avg_dynasty_rating` from optimal lineup |
| Starter Σ PPG | **35%** | `starter_total_ppg` |
| Age-weighted depth | **25%** | Youth factor vs positional peak ages (`dynasty_score._PEAK_AGE`): 65% starter-weighted + 35% top-4 bench by TV |

**Tier assignment** (within-league ranks on composite): top ⌈n/3⌉ → **Contender**, bottom ⌊n/3⌋ → **Rebuild**, middle → **Competitive**. On 10-team leagues that is ranks 1–4 / 5–7 / 8–10 (ceil(10/3)=4, floor(10/3)=3).

**Trade surplus:** top-3 / bottom-3 by position-strength rank; counterparties are complementary top/bottom teams per position.

Rationale on seeded leagues: age depth breaks ties when starter OVR and PPG cluster (e.g. GLA teams with similar 88–89 starter OVR but different bench youth). PPG weight rewards weekly ceiling without letting it dominate dynasty OVR.

### Resolved (Phase 1)

- **Startup-draft roster source:** When Sleeper `rosters[].players` is empty (league still in startup draft), sync falls back to grouping `draft_picks` by `roster_id`. In-season leagues use live Sleeper rosters.
- **Anchor universe vs scored players:** OVR anchors (TV max, per-game maxes, curve bounds) come from the **full fantasy player universe** with league scoring context applied — same idea as Pickbook's eligible board. **Snapshots** are written for rostered players plus top-N FAs by TV (§14.2). Draft progress must not shift another player's grade.

---

## 15. OVR trends & snapshot history

**Intent:** see how a player's grade moves — and *why* — across syncs within a league. Also: when dynasty weights, per-game tilt, or the rating curve change, **recompute historical OVR from stored inputs** instead of losing the past.

### 15.1 Store inputs, not just outputs

OVR is derived: `inputs → normalized components → dynasty_score (0–1 composite) → power curve + anchors → dynasty_rating (50–99)`.

History must persist the **inputs and intermediate state**, with the displayed OVR as a cache:

| Layer | Persist at sync | Why |
|-------|-----------------|-----|
| **Raw production** | HPPG, W/g, availability, `hppg_expected`, season WORP | Real-world change over time; independent of formula |
| **Market** | `trade_value` | TV moves; not formula-dependent |
| **Identity** | age, position, `years_exp` if available | Age curve changes affect re-grade |
| **Normalized components** | `components_json` (tv, worp, per_game, upside, age, trajectory) | What actually fed the composite |
| **Composite** | `dynasty_score` (pre-curve 0–1) | Re-apply new curve without re-ingesting Sleeper |
| **Cached grade** | `dynasty_rating`, `flex_rating` | Fast reads; display value at sync time |
| **Formula fingerprint** | `formula_version` (hash of `dynasty_weights` + `dynasty_rating_curve` from settings) | Know which formula produced the cached grade |
| **League anchors** | `context_hash` + anchor blob on `league_snapshot_history` (max TV, per-game maxes QB/flex, curve min/max) | OVR is league-relative; re-curve needs the anchor board that existed at sync time |

**Re-grade path:** given stored components (or raw inputs + anchors), run `curved_composite_to_rating()` with *today's* weights/curve → new OVR series for charts. Optionally batch job: `POST /admin/recompute-history` (personal tool; no auth theater, but gated).

**Two different "history" stories:**

1. **Player changed** — HPPG/TV/age moved; inputs differ row-to-row; trend is real.
2. **Formula changed** — inputs identical for a past sync; re-running curve changes OVR; UI can show "as of formula v2" vs "as originally synced."

Do **not** silently rewrite cached grades in history rows; append a recomputed view or store `dynasty_rating_recomputed` when formula changes so audit trail stays honest.

### 15.2 Guarantees

| Guarantee | Rule |
|-----------|------|
| Current OVR | Always from `player_snapshots` (consistency contract unchanged). |
| History | Append-only at sync; never overwrite prior rows. |
| Scope | Per `league_id` — no cross-league trend line (OVR scales differ). |
| Granularity | One player row + one league anchor row per successful sync. |

**UI (player page, mockup):** sparkline for OVR and/or HPPG; hover shows component deltas ("TV +0.04, per-game −0.02"). Toggle or footnote when viewing a re-graded series. Team/overview tiles: Δ OVR since last sync.

**Prerequisite:** scheduler (§9.1) — daily syncs make trends meaningful within a few weeks.

---

## 16. Opportunity model & projected PPG (custom)

**Intent:** honest **projected per-game production** grounded in *role and offense*, not just market TV or a single external projection feed. Feeds:

- "Projected PPG" on roster/lineup views (mockup team + overview sidebars).
- Expected PPG for rookies (augments §5.6 over time).
- Age/outlook timeline — where a player is on their arc *given opportunity* (mockup player page).
- Eventually forward OVR sketches (later; needs calibration).

### 16.1 What "opportunity" means

Opportunity = expected **volume share** within a scoring context:

| Signal | Examples | Source (bootstrap → custom) |
|--------|----------|----------------------------|
| **Offense environment** | plays/game, pass rate, pace, EPA | nflverse team stats |
| **Role share** | target share, air-yards share, rush share, routes, RZ touches | nflverse player-weekly |
| **Depth-chart context** | competition, injuries, additions | Sleeper depth + manual overrides later |
| **Archetype** | alpha WR, slot volume, committee RB, rushing QB | Derived cluster on production shape |

Projected PPG = `(expected volume) × (efficiency per opportunity) × (league scoring context)` — computed in Python at sync, stored on snapshot, read by UI.

### 16.2 Phased build (don't block portfolio/analysis)

| Stage | Approach | Honesty |
|-------|----------|---------|
| **v0 (today)** | Sleeper season projection ÷ 17; TV imputation fallback | `hppg_expected` flag |
| **v1** | nflverse trailing volume + team pace → opportunity score; blend with Sleeper | `projected_ppg` + `projection_source` |
| **v2** | Archetype labels + age/peak window from positional curves (reuse `_PEAK_AGE`, trajectory) | "Peak window" UI |
| **v3** | Proprietary model trained on historical volume→PPG; offense scheme features | Document weights in this book |

**Data appetite:** v1 needs player-weekly + team-weekly nflverse (cached). v3 needs multi-season history — start retaining sync history and optionally nflverse snapshots now so the training set grows.

**Design rule:** projected PPG is a **lens**, not a replacement for HPPG on the headline OVR unless explicitly toggled. Real snap-filtered production stays primary for in-season grades.

### 16.3 Archetype (lightweight, not ML-first)

Start with **rule-based archetypes** from normalized stats (high TV / low WORP = developmental; high W/g + low TV = undervalued producer; etc.). Clusters can come later. Archetype informs outlook copy and projection priors, not a second competing OVR.

---

*Execution — phases, tasks, file-level steps, acceptance criteria, deployment runbook — lives in `BLACKBOOK_TASKS.md`.*
