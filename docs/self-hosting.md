# Self-hosting on free tiers

This walks through a ₹0/month deployment: **Supabase** (database), **Render** (API), **Vercel** (web), **GitHub Actions** (scheduled ingest). Budget about 30 minutes. To run everything on one machine instead, use `docker compose` (see the README).

## 1. Database: Supabase

1. Create a free project at supabase.com.
2. **Project Settings → Database → Connection string → URI**, choose the **Transaction pooler** (port `6543`).
3. Change the scheme to `postgresql+asyncpg://`. This is your `DATABASE_URL`.

Migrations need the `pg_trgm` and `unaccent` extensions. Supabase allows both, and the baseline migration creates them.

## 2. Secrets you'll reuse

Generate one `SECRET_KEY` and use the **same value everywhere** (Render and GitHub Actions). It signs logins and encrypts stored SMTP app passwords:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Optional: an LLM for re-ranking, resume autofill and drafting. Either a `GEMINI_API_KEY` (Google AI Studio, free tier) or any OpenAI-compatible API through `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`, e.g. Groq's free tier or a local Ollama (`http://localhost:11434/v1`). Also optional: a `REDIS_URL` from Upstash for caching.

## 3. API: Render

1. Fork this repo. In Render choose **New → Blueprint** and select your fork. `render.yaml` defines the service.
2. Fill in the secrets Render prompts for: `DATABASE_URL`, `SECRET_KEY`, and optionally `REDIS_URL` and `GEMINI_API_KEY`. Leave `FRONTEND_URL`/`CORS_ORIGINS` until step 4.
3. Each deploy runs `alembic upgrade head`, so the first one builds the schema.
4. Create your admin. From your machine, with `DATABASE_URL` and `SECRET_KEY` exported:
   ```bash
   python -m scripts.create_admin --email you@example.com --name "Your Name"
   python -m scripts.seed_companies
   ```

The free instance sleeps after 15 idle minutes, so the first page load afterwards takes about 50 seconds.

## 4. Web: Vercel

1. **New Project** → import your fork → set **Root Directory** to `web`.
2. Environment variable: `API_BASE_URL` = your Render URL (e.g. `https://jobradar-api.onrender.com`).
3. Back in Render, set `FRONTEND_URL` to the Vercel URL and `CORS_ORIGINS` to `["https://<your-app>.vercel.app"]`.

## 5. Scheduled jobs: GitHub Actions

In your fork, go to **Settings → Secrets and variables → Actions**:

- **Secrets:** `DATABASE_URL`, `SECRET_KEY`, and optionally `REDIS_URL`, `GEMINI_API_KEY`. For digests, also add the email settings from step 6.
- **Variables:** `JOBRADAR_SCHEDULE` = `true`. Scheduled workflows stay off until you set this.

| Workflow | When (IST) | Does |
|---|---|---|
| `ingest` | 07:00, 13:00, 19:00 | Pull sources → enrich → match new jobs |
| `digest` | 08:00 daily, Mon 08:30 | Email top new matches / weekly summary |
| `outreach` | 09:30, 18:30 | Read replies and bounces, send queued follow-ups |
| `storage-maintenance` | 03:00 | Purge stale jobs, drop old raw payloads (keeps you under 500 MB) |

Change which sources each ingest run pulls with the variables `INGEST_SOURCES_FULL`, `INGEST_SOURCES_MIDDAY` and `INGEST_SOURCES_EVENING`. Run any workflow manually from the **Actions** tab.

## 6. Email (optional)

System email covers invites, digests and password resets:

- **Resend:** `EMAIL_TRANSPORT=resend`, `RESEND_API_KEY`, and `SES_FROM_EMAIL` on a domain you verified in Resend.
- **SMTP:** `EMAIL_TRANSPORT=smtp` plus `SMTP_HOST/PORT/USERNAME/PASSWORD`.

Without email, invites still work: the invite link is shown in **Settings → Team** for you to share yourself.

**Outreach email** is separate. Each user connects their own Gmail on the Outreach page with a Google App Password. Mail goes from their mailbox, and replies and bounces are read back over IMAP.

## 7. Invite people

**Settings → Team → Invite**. Each person sets their own password, creates their own profile, and gets their own feed. Their cities and target titles are added to what the scrapers search.

## Upgrading

Pull the latest changes and redeploy. Migrations run automatically, both on Render and in `docker compose up`.
