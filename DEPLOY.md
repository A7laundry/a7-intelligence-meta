# A7 Intelligence — Railway Deployment Guide

## Prerequisites

- Railway account at [railway.app](https://railway.app)
- GitHub repository connected to Railway
- Python 3.11+ (Nixpacks detects this automatically)

---

## Environment Variables

Set these in Railway → Service → Variables:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | **YES** | Random secret for Flask sessions. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `META_ACCESS_TOKEN` | YES | Long-lived Meta API access token |
| `META_AD_ACCOUNT_ID` | YES | Primary Meta ad account ID (e.g. `act_123456789`) |
| `META_AD_ACCOUNT_ID_BR` | Optional | Secondary Meta ad account ID |
| `META_APP_ID` | Optional | Meta App ID |
| `META_APP_SECRET` | Optional | Meta App Secret |
| `DEEPSEEK_API_KEY` | Optional | DeepSeek API key for AI features |
| `OPENROUTER_API_KEY` | Optional | OpenRouter API key |
| `ANTHROPIC_API_KEY` | Optional | Anthropic API key |
| `OPENAI_API_KEY` | Optional | OpenAI API key |
| `SLACK_WEBHOOK_URL` | Optional | Slack webhook for automation notifications |
| `NOTIFICATION_WEBHOOK_URL` | Optional | Generic webhook for events |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | Optional | Email notifications |
| `NOTIFICATION_EMAIL_TO` | Optional | Recipient email for alerts |
| `A7_DB_PATH` | Optional | Override SQLite path. **Set to `/data/a7_intelligence.db` if using a Railway Volume** |
| `A7_DISABLE_SCHEDULER` | Optional | Set to `1` to disable background scheduler |
| `FLASK_ENV` | Optional | Set to `production` (enables stricter warnings) |

---

## SQLite & Persistent Storage

Railway's default filesystem is **ephemeral** — data is lost on redeploy.

**Option A — Accept ephemeral DB (demo/dev use)**
- Do nothing. The DB resets on every deploy.

**Option B — Railway Volume (recommended for production)**
1. In Railway dashboard: Service → **Add Volume** → mount path `/data`
2. Set env var: `A7_DB_PATH=/data/a7_intelligence.db`
3. The database persists across deploys and restarts.

---

## Deploy Steps

### 1. Push to GitHub

```bash
git add .
git commit -m "feat: Railway deploy readiness"
git push origin main
```

### 2. Connect Railway

1. Go to [railway.app/new](https://railway.app/new)
2. Select **Deploy from GitHub repo**
3. Choose this repository
4. Railway auto-detects Python via Nixpacks and runs `pip install -r requirements.txt`

### 3. Set Environment Variables

In Railway dashboard → Service → Variables, set at minimum:
```
SECRET_KEY=<generated-32-char-hex>
META_ACCESS_TOKEN=<your-token>
META_AD_ACCOUNT_ID=act_<your-id>
FLASK_ENV=production
```

### 4. Deploy

Railway deploys automatically on push. To trigger manually:
```bash
# Via Railway CLI (optional)
railway up
```

### 5. Verify

```bash
# Replace with your Railway domain
curl https://your-app.railway.app/health
# Expected: {"status":"ok","version":"2.0.0","database":"connected",...}

curl https://your-app.railway.app/health/detailed
# Shows scheduler status, DB path, environment
```

Open `https://your-app.railway.app/` to see the dashboard.

---

## Deployment Checklist

- [ ] `SECRET_KEY` set in Railway variables
- [ ] `META_ACCESS_TOKEN` set
- [ ] `META_AD_ACCOUNT_ID` set (format: `act_XXXXXXXXX`)
- [ ] Railway Volume added and `A7_DB_PATH=/data/a7_intelligence.db` set (if persistent storage needed)
- [ ] `/health` returns `{"status":"ok"}`
- [ ] Dashboard loads at root URL
- [ ] No `SECRET_KEY not set` warning in Railway logs

---

## Scheduler Behavior

The background publishing scheduler starts automatically unless `A7_DISABLE_SCHEDULER=1`.

With `--workers 1` (the default in `Procfile` and `railway.json`), only one scheduler thread runs — this is safe for SQLite.

If you scale to multiple workers in the future, set `A7_DISABLE_SCHEDULER=1` and run the scheduler as a separate Railway service using:
```
python run.py --publishing-loop
```

---

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill env vars
cp .env.example .env

# Run (dev server on port 5050)
python run.py

# Or with Gunicorn (production-like)
gunicorn wsgi:app --bind 0.0.0.0:5050 --workers 1 --reload
```
