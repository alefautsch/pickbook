# Deploy Blackbook to Railway

Blackbook deploys as three Railway resources:

- PostgreSQL database
- `api` service from the repo root using `Dockerfile.blackbook`
- `web` service from `frontend/` using `frontend/Dockerfile`

Live rookie drafts run in Blackbook (`/leagues/[id]/rookie-draft`). The legacy Streamlit app (`just app`) remains in the repo for local engine debugging only — it is not deployed.

## 1. Create Railway resources

Create a Railway project with:

1. PostgreSQL plugin.
2. `api` service connected to this repo with root directory `/`.
3. `web` service connected to this repo with root directory `/frontend`.

## 2. Configure the API service

Use the repo-root `railway.toml` defaults:

| Setting          | Value                  |
| ---------------- | ---------------------- |
| Builder          | Dockerfile             |
| Dockerfile path  | `Dockerfile.blackbook` |
| Healthcheck path | `/health`              |

Set variables:

- `DATABASE_URL` (required): Railway Postgres URL; keep SQLAlchemy driver form if needed, e.g. `postgresql+psycopg://...`.
- `SLEEPER_USERNAME` (required): defaults locally to `alefautsch`.
- `CORS_ORIGINS` (required): public web URL, e.g. `https://blackbook-web.up.railway.app`.
- `ANTHROPIC_API_KEY` (optional): required only for advisor chat.
- `ADMIN_TOKEN` (optional): gates admin recompute endpoint when set.
- `FA_POOL_SIZE` (optional): defaults to `150`.
- `RUN_DB_MIGRATIONS` (optional): defaults to `true` in `scripts/start-blackbook-api.sh`.
- `SEED_DB` (optional): defaults to `true` in `scripts/start-blackbook-api.sh`.

The API container runs:

```bash
uv run alembic upgrade head
uv run python -m backend.seed
uv run uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
```

## 3. Configure the web service

Set the service root directory to `frontend/`. Railway should use `frontend/railway.toml`, which points at `frontend/Dockerfile`.

Set variables:

- `API_URL` (required): server-side API base URL. Prefer Railway private networking for server-rendered routes.
- `NEXT_PUBLIC_API_URL` (required): browser-visible API base URL used by client components like sync, search, advisor, and rookie draft polling. Use the API public URL unless those calls are proxied.

## 4. Configure scheduled sync

The API service runs the scheduled sync in-process. Set these variables on the API service:

```
SYNC_ENABLED=true
SYNC_CRON=0 11 * * *
```

Railway uses UTC; `0 11 * * *` is 6 AM at UTC-5. The scheduler uses a Postgres advisory lock before running, so duplicate API processes skip overlapping runs. The app also has a manual Sync button.

## 5. Verify after deploy

Check:

- `GET /health` returns API health.
- `GET /leagues` returns the three seeded leagues.
- The web service loads a league dashboard.
- Manual Sync completes and `/sync/status` shows success.
- Scheduled sync writes new `sync_runs` rows after the next `SYNC_CRON` fire.
