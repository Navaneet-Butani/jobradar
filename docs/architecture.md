# Architecture

```
┌────────────── SOURCE ADAPTERS  app/integrations/<source>/ ──────────────┐
│ ats (greenhouse·lever·ashby) · instahyre · hirist · jobspy (indeed)     │
│ linkedin · remotive · himalayas · arbeitnow · remoteok                  │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ RawJobData (original payload kept)
                                ▼
            JobProcessor  app/services/job_processor.py
   FieldMapping extraction → salary / location / skills / experience parsing
   → content hash + cross-source dedup → company resolution → store
                                │
                                ▼
             PostgreSQL ── raw payload enrichment  app/services/enrichment/
                                │
                                ▼
            Matching  app/services/matching/
   hard filters → weighted 0–100 score → noise rules → optional LLM re-rank
                                │  matches table
                                ▼
            FastAPI  app/api/<module>/  ──►  Next.js  web/
```

**Ingest is decoupled from serving.** Scrapers run as scripts (`scripts/run_ingest.py`) on GitHub Actions or cron. The API and web app only read the database. A blocked or slow source never affects a page load.

## Ingest

`scripts/run_ingest.py --sources a,b,c` runs each source's fetcher, then two follow-up passes over the new rows:

1. **Enrichment** (`app/services/enrichment/raw_backfill.py`) mines the stored raw payloads for logos, company websites, ratings and stated experience. It makes no network calls and only fills NULL columns.
2. **Matching** (`app/services/matching/engine.py`) scores the new jobs against every active profile.

Each fetcher emits `RawJobData` (`app/models/source.py`) and hands batches to `JobProcessor.process_job_batch`, which processes about 10 jobs concurrently with one DB session per job. Ingest sets a 10+10 connection pool by itself; the API runs on a small 3+2 pool.

**What gets searched** for the keyword-driven sources (JobSpy, LinkedIn, Hirist) comes from `app/services/search_targets.py`: the union of all active profiles' `cities`, `metro_cities` and `target_titles`. With no profiles yet, it falls back to India's main tech hubs plus the search terms of the role categories enabled under **Settings → Scraping**. The ATS adapter walks whole company boards, so it filters titles through the role allowlist in `app/services/role_filter.py`.

**ATS discovery** (`app/integrations/ats/discovery.py`): when any source surfaces a company without a known board, discovery probes Greenhouse, Lever, Ashby, SmartRecruiters and Recruitee for slug variants. A hit is polled directly from then on. Ambiguous short slugs ("pine" for "Pine Labs") are only accepted when Greenhouse's board name matches the company, and SmartRecruiters/Recruitee hits always require a matching display name.

## Deduplication

`app/services/deduplication/` and `app/services/deduplication_service.py`:

- Exact match on a content hash, checked first against a Redis bloom filter when Redis is configured. Without Redis, every check goes to the database.
- Fuzzy title/company/location similarity for the same job across sources (`cross_source_detector.py`).
- On merge, the best apply URL wins: ATS → company careers page → Instahyre → LinkedIn → Indeed → other aggregators.

## Matching

| Stage | Where | What |
|---|---|---|
| Hard filters | `filters.py` | Location/remote scope, experience band and seniority ceiling, excluded keywords and companies, at least one must-have skill |
| Score (0–100) | `scoring.py` | skills 35 · title 20 · experience 15 · location 10 · freshness 10 · salary 5 · source quality 5 |
| Noise rules | `noise.py` | Staffing/C2H −15, stack spam −10, ghost reposts up to −15, mandatory CS degree −5 (if the profile sets `no_cs_degree`), preferred domain +5 |
| LLM re-rank | `llm_rerank.py` | Optional. Blends 70% rule score with 30% LLM score and adds a one-line reason |

Cities are compared by canonical name (`canonical_city`: Bangalore = Bengaluru = "Hosur Road Bangalore", Gurgaon = Gurugram). Terms match on whole words (`contains_term`), so "go" doesn't match "good" and "java" doesn't match "javascript". Every component is stored in `matches.reasons`, which is what the UI's score breakdown shows.

## LLM

`app/services/llm/gemini.py` is the one client every AI feature uses. It talks to any OpenAI-compatible `/chat/completions` endpoint when `LLM_BASE_URL` is set, otherwise to Gemini. Every caller degrades to non-AI behaviour when no LLM is configured or a call fails. `app/services/resume_profile.py` suggests profile fields from a resume: heuristics first, then a validated LLM overlay.

## API

The three-file pattern per module, in `app/api/<module>/`:

- `api.py`: router and endpoints, decorated with `@log_api_call` / `@standardize_response`.
- `schema.py`: Pydantic models.
- `service.py`: business logic and DB access.

Responses use `APIResponse` (`app/core/responses.py`). Routers are registered in `app/main.py`.

The browser never calls the API directly. Next.js server components and route handlers call it with an httpOnly session cookie (`web/lib/backend.ts`).

## Data and retention

The schema lives in Alembic (`alembic/versions/`). The baseline creates extensions, the `job_search` text-search config, tables, SQL functions and triggers. `scripts/storage_maintenance.py` purges jobs unseen for 60 days, unless a match or application references them, and drops raw payloads after 7 days, which keeps a free 500 MB database comfortable.

## Known rough edges

- **Inherited code.** Much of `app/` comes from an earlier, larger job-portal codebase, so some modules are more elaborate than this product needs. Prefer adding sources and features over refactoring working inherited code.
- **Experience provenance.** When a source doesn't state experience, it's inferred from the description or title ("Senior" → 5+). The UI doesn't yet distinguish inferred figures from stated ones.
- **Instahyre descriptions.** Instahyre publishes no job descriptions, so its jobs score on title and skills only.
