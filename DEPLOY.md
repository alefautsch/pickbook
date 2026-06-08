# Deploy Blackbook to Railway

Blackbook deploys as three Railway resources:

- PostgreSQL database
- `api` service from the repo root using `Dockerfile.blackbook`
- `web` service from `frontend/` using `frontend/Dockerfile`

Legacy Pickbook remains a local Streamlit app for now (`just pickbook`). The Blackbook sidebar only shows the Pickbook link in local development unless `NEXT_PUBLIC_PICKBOOK_URL` is explicitly set.

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
- `NEXT_PUBLIC_PICKBOOK_URL` (optional): leave unset to hide Pickbook in production. Set only if deploying legacy Pickbook separately.

## 4. Configure scheduled sync

Use Railway Cron or a small cron service to trigger one of:

```bash
curl -X POST "$API_PUBLIC_URL/sync"
```

or:

```bash
python -m backend.sync_cli
```

Daily is enough for portfolio/history. The app also has a manual Sync button.

## 5. Verify after deploy

Check:

- `GET /health` returns API health.
- `GET /leagues` returns the three seeded leagues.
- The web service loads a league dashboard.
- Manual Sync completes and `/sync/status` shows success.
- Daily cron writes new `sync_runs` rows.

---

## Legacy Pickbook Railway notes

## 1. Push to GitHub

```bash
cd /Users/afautsch/dc
git init
git add .
git commit -m "Pickbook: mobile dynasty draft assistant"
git remote add origin https://github.com/alefautsch/pickbook.git
git push -u origin main
```

## 2. Create Railway service

1. [railway.com](https://railway.com) → **New Project** → **Deploy from GitHub repo** → `alefautsch/pickbook`
2. Railway detects the `Dockerfile` automatically.

## 3. Set environment variables

In Railway → your service → **Variables**:

| Variable            | Required | Example                           |
| ------------------- | -------- | --------------------------------- |
| `ANTHROPIC_API_KEY` | Yes      | `sk-ant-...`                      |
| `SLEEPER_USERNAME`  | No       | `alefautsch` (default in app)     |
| `LEAGUE_ID`         | No       | `1314731206859853824`             |
| `DRAFT_ID`          | No       | `1314734674332880896`             |
| `SEASON`            | No       | `2026`                            |

Defaults are baked in for Good Luck Assholes — you only need `ANTHROPIC_API_KEY` if those IDs stay the same.

## 4. Generate domain

Railway → service → **Settings** → **Networking** → **Generate Domain**.

Open that URL on your phone. Add to home screen for an app-like shortcut (Safari: Share → Add to Home Screen).

## 5. CLI deploy (alternative)

```bash
railway login
railway link          # pick project
railway variable set ANTHROPIC_API_KEY=sk-ant-...
railway up --detach
railway domain
```

## Notes

- `war.csv` ships in the Docker image — no object storage needed.
- Settings saved in the UI write to ephemeral disk on Railway; use env vars for production config.
- Slow draft: enable **Auto-refresh** in Settings (default on, 20s).
