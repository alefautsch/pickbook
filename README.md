# Dynasty Blackbook

Personal dynasty research hub (Next.js + FastAPI + Postgres) across three Sleeper leagues. Design: `BLACKBOOK.md` · tasks: `BLACKBOOK_TASKS.md`.

**Live rookie drafts** run in Blackbook at `/leagues/[id]/rookie-draft` — BPA board, needs, value-pivot alerts, mock timeline, auto-poll.

**Scoring engine:** `dynasty_draft/` — dynasty OVR, HPPG, WORP, projections, lineup optimization. Shared library for Blackbook and the legacy Streamlit app.

## Quick start (Blackbook)

```bash
just install
just bb-db          # Postgres via docker-compose
just bb-api         # FastAPI on :8000
just bb-web         # Next.js on :3000
just bb-sync-all    # Sleeper → Postgres
```

## Legacy Streamlit app (local only)

The original Pickbook UI (`dynasty_draft/app.py`) is kept for engine debugging — not deployed.

```bash
just app            # Streamlit on :8501
just sync           # CLI one-shot draft sync
just watch          # CLI live draft poll
```

See `.env.example` for `ANTHROPIC_API_KEY`, `DATABASE_URL`, etc. Deploy notes: `DEPLOY.md`.
