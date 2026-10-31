"""Greenhouse board API fetch."""

import logging
from datetime import datetime
from typing import Dict, Any, List

from .client import ATSClient, ATSNotFoundError

logger = logging.getLogger(__name__)


async def fetch_greenhouse_jobs(client: ATSClient, slug: str, company_name: str) -> List[Dict[str, Any]]:
    """Fetch all open jobs for a company's Greenhouse board.

    Returns [] if the slug doesn't exist (no board on Greenhouse) — that's
    a normal, expected outcome, not an error.
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

    try:
        response = await client.get(url, identifier="greenhouse")
    except ATSNotFoundError:
        return []

    data = response.json()
    jobs = data.get('jobs', [])

    for job in jobs:
        job['_company_name'] = company_name
        job['_apply_url'] = job.get('absolute_url')
        job['_location'] = (job.get('location') or {}).get('name')
        # updated_at is ISO8601 with a numeric offset (e.g. "-04:00"), which
        # FieldExtractor's strftime-based date parser doesn't understand —
        # strip the offset so it parses as a plain naive timestamp.
        updated_at = job.get('updated_at')
        if isinstance(updated_at, str) and len(updated_at) >= 19:
            job['_posted_date'] = updated_at[:19]

    logger.info(f"Fetched {len(jobs)} Greenhouse jobs for '{slug}'")
    return jobs
