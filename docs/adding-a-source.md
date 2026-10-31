# Adding a source

Most sources are **configuration, not code**. An adapter fetches pages and emits `RawJobData`; `JobProcessor` does everything else (extraction, normalisation, dedup, storage).

## 1. Copy the closest adapter

Small JSON APIs: copy `app/integrations/remotive/`. Paginated or keyword-driven searches: copy `app/integrations/hirist/`.

```
app/integrations/<source>/
├── __init__.py
├── config.py      FieldMapping + setup_<source>_source() (registers the job_sources row)
├── client.py      httpx client, typed errors, tenacity retries
└── fetcher.py     pagination → RawJobData → job_processor.process_job_batch()
```

Use `app/integrations/_common/rate_limiter.py` for politeness limits. These are free endpoints; keep it to about 1 request per second unless the API says otherwise.

## 2. Map fields declaratively

`RawJobData.extract_field()` resolves values through a `FieldMapping`, with dot-notation for nested keys. The first key that exists wins:

```python
FieldMapping(
    title=["title", "position"],
    company=["employer.company_name", "company"],   # nested
    location=["locations", "location"],
    apply_url=["apply_url", "url"],
    description=["description"],
    skills_required=["keywords"],
    posted_date=["created_at"],
)
```

Always put the **complete original payload** in `RawJobData.raw_data`. If the payload carries more than the mapping covers (logo, company website, stated experience), add an extractor to `app/services/enrichment/raw_backfill.py`.

## 3. Search with the users' targets

Keyword-driven sources should search for what the users want, not a hardcoded list:

```python
from ...services.search_targets import load_search_targets
targets = await load_search_targets()   # .cities, .metro_cities, .terms, .locations()
```

Sources that return whole boards (like the ATS adapter) should filter titles with `app.services.role_filter.is_it_role()`.

## 4. Wire it up

1. Add a `run_<source>()` function and an `ALL_SOURCES` entry in `scripts/run_ingest.py`.
2. Add it to a source list in `.github/workflows/ingest.yml` if it should run on schedule.
3. Optionally give it a weight in `SOURCE_QUALITY` (`app/services/matching/scoring.py`).
4. Add a row to the table in `docs/sources.md`.

## 5. Verify

```bash
python -m scripts.run_ingest --sources <source>
```

Check the summary (`Seen / Added / Duplicate`), then look at a few rows on the Search page: title, company, location, description and apply link. A second run should add close to nothing.
