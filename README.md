# Pickbook

Mobile-first dynasty draft assistant. Deploy to Railway for phone access during slow drafts.

# Dynasty Draft Assistant (local dev)

Sync your live Sleeper dynasty startup against `war.csv` (dynasty-daddy WORP + trade values). Built for **vet-only startup** leagues with a **reversed rookie draft**.

## Setup with uv

```bash
cd /Users/afautsch/dc
just install   # or: uv sync
```

## Streamlit UI (recommended during draft)

```bash
just app       # or: just run
```

`just` loads `.env` automatically. Streamlit is configured to **reload the app when you save Python files** (see `.streamlit/config.toml`). If file watching doesn't work on your machine, use `just app-poll`.

In-app **Sync draft** and sidebar **Auto-refresh** handle live Sleeper pick updates during the draft.

Preconfigured for **Good Luck Assholes** (`alefautsch`, 2026 dynasty superflex startup).

Sidebar: Sleeper connection, scoring weights, vet/rookie strategy, **Anthropic API key** for the AI advisor.

### AI pick advisor

At snake bookends (picks 10 & 11, 30 & 31, …) click **Ask Claude** for a two-pick pairing plan. The prompt includes your roster, tier cliffs, superflex format, and live board state.

API key: add `ANTHROPIC_API_KEY=sk-ant-...` to `.env` in the project root (see `.env.example`). Sidebar can override per session.

## CLI

```bash
uv run dynasty-draft setup
uv run dynasty-draft sync
uv run dynasty-draft watch
uv run dynasty-draft insights
```

## Config (`config.json`)

| Field | Purpose |
|-------|---------|
| `sleeper_username` | Your Sleeper handle |
| `draft_id` / `league_id` | Draft to track |
| `trade_weight` / `worp_weight` | Balance trade capital vs win-now WORP |
| `strategy.draft_phase` | `vets` (startup) or `rookies` |
| `strategy.startup_slot` | `10` for pick 1.10 |
| `strategy.rookie_draft_slot` | `1` when rookie order is reversed |

Copy `config.example.json` to `config.json` and edit, or use `setup` / the Streamlit sidebar.

## How picks are ranked

1. Normalize trade value + WORP (+ spike upside)
2. Value over replacement by position
3. Starter needs from roster slots
4. Tier cliffs surfaced in UI/CLI
