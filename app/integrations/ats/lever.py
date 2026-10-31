"""Lever postings API fetch."""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from .client import ATSClient, ATSNotFoundError, ATSAPIError

logger = logging.getLogger(__name__)


async def fetch_lever_jobs(client: ATSClient, slug: str, company_name: str) -> List[Dict[str, Any]]:
    """Fetch all open postings for a company's Lever board.

    Returns [] if the slug doesn't exist — that's a normal, expected
    outcome, not an error.
    """
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"

    try:
        response = await client.get(url, identifier="lever")
    except ATSNotFoundError:
        return []

    try:
        jobs = response.json()
    except ValueError:
        raise ATSAPIError(f"Invalid JSON from Lever for '{slug}'")

    if not isinstance(jobs, list):
        return []

    for job in jobs:
        job['_company_name'] = company_name
        job['_apply_url'] = job.get('applyUrl') or job.get('hostedUrl')
        categories = job.get('categories') or {}
        job['_location'] = categories.get('location')
        # createdAt is epoch milliseconds — FieldExtractor's date parser only
        # understands strftime formats, so convert it here.
        created_at = job.get('createdAt')
        if isinstance(created_at, (int, float)):
            try:
                job['_posted_date'] = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            except (ValueError, OSError):
                job['_posted_date'] = None

    logger.info(f"Fetched {len(jobs)} Lever jobs for '{slug}'")
    return jobs
