# Deploy Pickbook to Railway

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

| Variable | Required | Example |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | `sk-ant-...` |
| `SLEEPER_USERNAME` | No | `alefautsch` (default in app) |
| `LEAGUE_ID` | No | `1314731206859853824` |
| `DRAFT_ID` | No | `1314734674332880896` |
| `SEASON` | No | `2026` |

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
