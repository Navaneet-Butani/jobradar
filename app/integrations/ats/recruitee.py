"""Recruitee public offers API: https://<slug>.recruitee.com/api/offers/ (one call, full descriptions)."""

import logging
from datetime import datetime
from typing import Any, Dict, List

from .client import ATSAPIError, ATSClient, ATSNotFoundError

logger = logging.getLogger(__name__)


def _posted(value) -> str | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC").strftime("%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return None


async def _offers(client: ATSClient, slug: str) -> List[Dict[str, Any]]:
    try:
        response = await client.get(f"https://{slug}.recruitee.com/api/offers/", identifier="recruitee")
    except ATSNotFoundError:
        return []
    try:
        return response.json().get("offers") or []
    except (ValueError, AttributeError):
        raise ATSAPIError(f"Invalid JSON from Recruitee for '{slug}'")


async def fetch_recruitee_jobs(client: ATSClient, slug: str, company_name: str) -> List[Dict[str, Any]]:
    offers = [o for o in await _offers(client, slug) if o.get("status", "published") == "published"]
    for job in offers:
        job["_company_name"] = company_name
        job["_location"] = ", ".join(filter(None, [job.get("location"), "Remote" if job.get("remote") else None]))
        job["_apply_url"] = job.get("careers_apply_url") or job.get("careers_url")
        job["_posted_date"] = _posted(job.get("published_at"))
        job["description"] = "\n".join(filter(None, [job.get("description"), job.get("requirements")])) or None
    logger.info(f"Fetched {len(offers)} Recruitee jobs for '{slug}'")
    return offers


async def board_company_name(client: ATSClient, slug: str) -> str | None:
    """The board's display name if the subdomain exists and has offers (used by discovery)."""
    try:
        offers = await _offers(client, slug)
    except ATSAPIError:
        return None
    return (offers[0].get("company_name") if offers else None) or None
