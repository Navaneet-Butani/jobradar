# Contributing

Thanks for helping! Small, focused pull requests are the easiest to review.

## Good first contributions

- **Companies:** add rows to `data/companies.csv` (`name,ats_type,ats_slug,region`). To find a slug, open the company's careers page. A URL like `boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>` or `jobs.ashbyhq.com/<slug>` gives you both the type and the slug.
- **Sources:** see [docs/adding-a-source.md](docs/adding-a-source.md). Indian ATS platforms (Zoho Recruit, Keka, Darwinbox, Freshteam) are especially welcome.
- **Matching rules:** false positives and negatives in the feed. Include the job title and description snippet that was mis-scored.

## Development setup

```bash
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # DATABASE_URL to a local Postgres, any SECRET_KEY
alembic upgrade head
pytest -q                       # fast, no database needed
cd web && npm ci && npm run lint && npm run build
```

Or run the whole stack with `docker compose up -d --build`.

## Conventions

- Async everywhere: SQLAlchemy async and `httpx`, never `requests`. Log through `logging`, never `print()` (except in CLI scripts).
- API modules follow `api.py` / `schema.py` / `service.py`, and responses use `APIResponse` from `app/core/responses.py`.
- Every source adapter stores its raw payload and has a rate limiter.
- Schema changes go through Alembic: `alembic revision --autogenerate -m "..."`. CI runs `alembic check`, so models and migrations must agree.
- Add a test in `tests/` for any matching or parsing logic you change.
- Don't add infrastructure (queues, caches, metrics) without discussing it in an issue first. The project deliberately runs on free tiers.

## Non-goals

- Auto-applying to jobs: JobRadar prepares, the human sends.
- Scraping personal profiles or any personal data.
- Public signup, billing or multi-tenant SaaS features.
