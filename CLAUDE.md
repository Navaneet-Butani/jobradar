# CLAUDE.md

Guidance for AI coding assistants (and humans) working in this repository.

## What this is

JobRadar: a self-hosted job radar for Indian IT/software roles. It ingests jobs from several sources, deduplicates and normalises them, scores each job against a user's profile, and provides a ranked feed, search, application tracker and outreach tools. It's designed to run on free tiers (Supabase, Render, Vercel, GitHub Actions).

Read first: `README.md`, `docs/architecture.md`, `docs/sources.md`, `docs/adding-a-source.md`.

## Ground rules

1. **Prefer adding over refactoring.** The ingest path (`app/services/job_processor.py`), dedup engine (`app/services/deduplication/`) and auth were inherited from a larger codebase and work. Fix bugs at their root, but don't restructure them for style.
2. **No new infrastructure** (queues, caches, metrics exporters, new hosted services) without an issue discussing it. Free-tier deployability is a feature.
3. **Follow existing patterns.** Match the surrounding code; don't introduce new libraries or conventions.
4. **Store raw source payloads.** Sources change shape without warning; raw payloads let us re-parse.
5. **Re-verify source endpoints before building against them.** Undocumented APIs rot.
6. **Ingest is decoupled from serving.** The web app and API never call a scraper.
7. **Nothing user-specific in code.** Cities, titles and preferences come from `job_profiles`; search targets come from `app/services/search_targets.py`.

## Non-goals

- Auto-applying to jobs. Outreach email exists, but a human composes, previews and sends it from their own mailbox. No code path submits an application form.
- Scraping personal profiles or personal data. Job posts only.
- Naukri and HiringCafe integrations (blocked; see `docs/sources.md`).
- Public signup, billing, multi-tenancy, marketing pages.

## Stack

- Python **3.12** (not 3.13+: pinned `asyncpg`/`pandas` lack wheels), FastAPI 0.115, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic.
- PostgreSQL (needs `pg_trgm`, `unaccent`). Redis is optional.
- Next.js (App Router) + Tailwind in `web/`. See `web/AGENTS.md`: this Next.js version differs from older training data.

## Conventions

- API modules: `app/api/<module>/{api,schema,service}.py`, routers registered in `app/main.py`, responses via `APIResponse` (`app/core/responses.py`).
- Async everywhere; `httpx`, never `requests`. Structured logging via `logging`, no `print()` outside CLI scripts.
- Typed exceptions from `app/core/exceptions.py`. Retries with `tenacity`. A rate limiter on every source adapter.
- Source adapters prefer a declarative `FieldMapping` (`app/models/source.py`) over hand-written parsers.
- Schema changes: `alembic revision --autogenerate -m "..."`. CI runs `alembic check`. Never `create_all()`.

## Commands

```bash
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000          # /docs
pytest -q                                          # unit tests, no DB needed
python -m scripts.create_admin --email you@example.com
python -m scripts.run_ingest --sources ats,hirist,jobspy
python -m scripts.run_matching
cd web && npm run dev
docker compose up -d --build                       # whole stack
```

## Security

- Never commit `.env`; mirror new settings into `.env.example` with a safe default.
- Never log credentials, tokens or connection URLs.
- Profiles, resumes and applications are personal data. Don't send them anywhere beyond the configured LLM calls.
