"""Fetch the job descriptions that a source's list endpoint leaves out.

Three of our sources return no description at all in their feeds:

  * **Hirist** (4,496 jobs) — the search endpoint omits it, but the detail
    endpoint the job page calls after hydration returns the full JD as
    `data.introText`. Recoverable, and this module recovers it.
  * **LinkedIn** — the guest search endpoint returns cards only. The guest
    detail endpoint returns the full posting with no login. Same deal:
    one request per job, so it belongs here rather than in the sweep.
  * **Instahyre** (8,615 jobs) — neither the list endpoint nor the per-job
    API resource carries a description, and the public job page answers 403
    to anything that is not a real browser session. Not recoverable without
    scraping behind a bot wall, which we are not doing. Those jobs keep their
    skills list and employer blurb, and the UI says so plainly.

Descriptions are fetched one job at a time behind the source's own rate
limiter, and stored under the same byte budget the ingest pipeline uses so a
backfilled row costs no more than an ingested one.
"""

import logging
from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Same budget the pipeline applies on ingest (job_processor.MAX_DESCRIPTION_BYTES).
MAX_DESCRIPTION_BYTES = 4096

# Commit every N stored rows so a long run survives an interruption.
COMMIT_EVERY = 25

# Sources whose descriptions can be recovered after the fact.
FETCHABLE_SOURCES = ("hirist", "linkedin")

_SELECT_MISSING = text("""
    SELECT j.id, j.external_id
    FROM jobs j
    JOIN job_sources s ON s.id = j.source_id
    LEFT JOIN job_details d ON d.job_id = j.id
    WHERE s.name = :source
      AND j.status = 'active'
      AND coalesce(length(d.description), 0) < 50
    ORDER BY j.first_seen_at DESC
    LIMIT :limit
""")

_STORE = text("""
    INSERT INTO job_details (job_id, description)
    VALUES (:job_id, :description)
    ON CONFLICT (job_id) DO UPDATE SET description = EXCLUDED.description
""")

_STORE_EXPERIENCE = text("""
    UPDATE jobs SET min_exp_years = :min_years, max_exp_years = :max_years
    WHERE id = :job_id
""")


def _truncate_bytes(value: Optional[str], max_bytes: int = MAX_DESCRIPTION_BYTES) -> Optional[str]:
    """Truncate to a UTF-8 byte budget without splitting a multi-byte char."""
    if not value:
        return None
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


async def _fetch_hirist(client, external_id: str) -> Optional[str]:
    """One job's description HTML, or None if it is gone or empty."""
    try:
        payload = await client.fetch_detail(external_id)
    except Exception as e:
        logger.warning(f"Hirist detail fetch failed for {external_id}: {e}")
        return None
    if not payload:
        return None
    return _truncate_bytes(payload.get("introText"))


async def _fetch_linkedin(client, external_id: str) -> Optional[str]:
    try:
        payload = await client.fetch_description(external_id)
    except Exception as e:
        logger.warning(f"LinkedIn detail fetch failed for {external_id}: {e}")
        return None
    if not payload:
        return None
    return _truncate_bytes(payload.get("description_html") or payload.get("description_text"))


async def _reparse_experience(session: AsyncSession, job_id: int, description: str) -> bool:
    """Re-derive the experience range now that a description exists.

    Ingest ran before this description did, so whatever is in the column came
    from the job title — "Senior/Lead/Principal" all collapse to a flat 5+.
    A description that states a number outranks that guess, so only explicit
    numeric parses are written back; a second title-level guess changes
    nothing and is skipped.
    """
    from ...services.experience_parser import ExperienceParser

    parsed = ExperienceParser().parse_experience(description)
    if not parsed.parsing_method.startswith("numeric"):
        return False

    await session.execute(_STORE_EXPERIENCE, {
        "job_id": job_id,
        "min_years": parsed.min_years,
        "max_years": parsed.max_years,
    })
    return True


def _client_and_fetcher(source: str):
    """(client context manager, fetch coroutine) for a fetchable source.

    Imported lazily and per source so a broken integration can never take down
    an unrelated backfill, or the API process that imports this module.
    """
    if source == "hirist":
        from ...integrations.hirist.client import HiristClient
        return HiristClient(), _fetch_hirist
    if source == "linkedin":
        from ...integrations.linkedin.client import LinkedInClient
        return LinkedInClient(), _fetch_linkedin
    raise ValueError(f"No description fetcher for source '{source}'")


async def backfill_descriptions(
    session: AsyncSession,
    *,
    source: str = "hirist",
    limit: int = 200,
) -> Dict[str, int]:
    """Fetch and store descriptions for jobs that have none.

    Newest jobs first — those are the ones anyone is going to open. Returns
    counts so a scheduled run can report what it did.
    """
    source = source.lower()
    if source not in FETCHABLE_SOURCES:
        raise ValueError(f"No description fetcher for source '{source}'")

    rows = (await session.execute(_SELECT_MISSING, {"source": source, "limit": limit})).mappings().all()
    if not rows:
        return {"considered": 0, "fetched": 0, "stored": 0}

    client_ctx, fetch = _client_and_fetcher(source)

    # Commit as we go. A full run is thousands of rate-limited requests and the
    # better part of an hour; holding it all in one transaction would throw the
    # whole run away on any failure, and show nothing until it finished.
    stored = 0
    experience_fixed = 0
    async with client_ctx as client:
        for index, row in enumerate(rows, start=1):
            description = await fetch(client, row["external_id"])
            if not description:
                continue
            await session.execute(_STORE, {"job_id": row["id"], "description": description})
            stored += 1
            if await _reparse_experience(session, row["id"], description):
                experience_fixed += 1
            if stored % COMMIT_EVERY == 0:
                await session.commit()
                logger.info("Description backfill (%s): %s/%s stored", source, stored, index)

    await session.commit()

    logger.info(
        "Description backfill (%s): considered=%s stored=%s experience_updated=%s",
        source, len(rows), stored, experience_fixed,
    )
    return {
        "considered": len(rows), "fetched": stored, "stored": stored,
        "experience_updated": experience_fixed,
    }


async def fetch_description_for_job(session: AsyncSession, job_id: int) -> Optional[str]:
    """On-demand fetch for a single job, used when someone opens a job page
    that has no description yet. Stores what it finds, so the second visit and
    every later one is free."""
    row = (await session.execute(text("""
        SELECT s.name AS source_name, j.external_id
        FROM jobs j JOIN job_sources s ON s.id = j.source_id
        WHERE j.id = :job_id
    """), {"job_id": job_id})).mappings().first()

    if not row or row["source_name"] not in FETCHABLE_SOURCES:
        return None

    client_ctx, fetch = _client_and_fetcher(row["source_name"])

    try:
        async with client_ctx as client:
            description = await fetch(client, row["external_id"])
    except Exception as e:
        logger.warning(f"On-demand description fetch failed for job {job_id}: {e}")
        return None

    if not description:
        return None

    await session.execute(_STORE, {"job_id": job_id, "description": description})
    await _reparse_experience(session, job_id, description)
    await session.commit()
    return description
