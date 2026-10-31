"""Auto-discovery of ATS boards for companies we don't have one for yet.

Whenever any source (Instahyre, JobSpy, ...) surfaces a company name we
haven't matched to a Greenhouse/Lever/Ashby board, probe for one. On a
hit, the company list grows itself — this is the highest-leverage
mechanism in the whole ingest system (docs/sources.md).
"""

import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple

from rapidfuzz import fuzz

from .client import ATSClient, ATSNotFoundError, ATSAPIError
from .greenhouse import fetch_greenhouse_jobs
from .lever import fetch_lever_jobs
from .ashby import fetch_ashby_jobs
from ...repositories.company_repository import CompanyRepository

logger = logging.getLogger(__name__)

CORPORATE_SUFFIX_PATTERN = re.compile(
    r'\b(pvt|private|ltd|limited|inc|llc|technologies|tech|labs|solutions|software|systems)\b',
    re.IGNORECASE
)

# Don't re-probe a company we already tried this recently.
REDISCOVERY_COOLDOWN_DAYS = 30


def slug_variants(name: str) -> List[str]:
    """Candidate ATS slugs, most specific first: "Pine Labs" -> pinelabs, pine-labs, pine."""
    full = re.sub(r'[^a-z0-9]+', '', name.lower())
    hyphenated = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    base = CORPORATE_SUFFIX_PATTERN.sub('', name.lower()).strip()
    variants = [
        full,
        hyphenated,
        re.sub(r'[^a-z0-9]+', '-', base).strip('-'),
        re.sub(r'[^a-z0-9]', '', base),
    ]
    seen = set()
    unique = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def _is_ambiguous(slug: str, company_name: str) -> bool:
    """A suffix-stripped single short word ("pine" from "Pine Labs", "future"
    from "Future Tech") is very likely someone else's board. Such slugs are
    only accepted when the board's own display name matches the company."""
    return slug != re.sub(r'[^a-z0-9]+', '', company_name.lower()) and '-' not in slug and len(slug) < 8


async def _greenhouse_name_matches(client: ATSClient, slug: str, company_name: str) -> bool:
    try:
        response = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}", identifier="greenhouse")
        board_name = str(response.json().get("name") or "")
    except (ATSAPIError, ValueError, AttributeError):
        return False
    return fuzz.ratio(board_name.lower(), company_name.lower()) >= 85


async def discover_ats(client: ATSClient, company_name: str) -> Optional[Tuple[str, str]]:
    """Probe Greenhouse, then Lever, then Ashby for each slug variant. Returns (ats_type, slug) or None."""
    for slug in slug_variants(company_name):
        if _is_ambiguous(slug, company_name):
            # Only Greenhouse exposes a board name we can verify against.
            if await _greenhouse_name_matches(client, slug, company_name):
                return ("greenhouse", slug)
            continue
        try:
            jobs = await fetch_greenhouse_jobs(client, slug, company_name)
            if jobs or await _greenhouse_board_exists(client, slug):
                return ("greenhouse", slug)
        except ATSAPIError as e:
            logger.debug(f"Greenhouse probe error for '{slug}': {e}")

        try:
            jobs = await fetch_lever_jobs(client, slug, company_name)
            if jobs:
                return ("lever", slug)
        except ATSAPIError as e:
            logger.debug(f"Lever probe error for '{slug}': {e}")

        try:
            jobs = await fetch_ashby_jobs(client, slug, company_name)
            if jobs:
                return ("ashby", slug)
        except ATSAPIError as e:
            logger.debug(f"Ashby probe error for '{slug}': {e}")

    return None


async def _greenhouse_board_exists(client: ATSClient, slug: str) -> bool:
    """A Greenhouse board can exist with zero open jobs — 200 with an empty list is still a real board."""
    try:
        await client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", identifier="greenhouse")
        return True
    except ATSNotFoundError:
        return False
    except ATSAPIError:
        return False


async def discover_and_save_ats(company_id: int, company_name: str,
                                 client: Optional[ATSClient] = None,
                                 company_repo: Optional[CompanyRepository] = None) -> Optional[Tuple[str, str]]:
    """Discover a company's ATS board (if any) and persist the result."""
    company_repo = company_repo or CompanyRepository()

    async def _run(c: ATSClient):
        result = await discover_ats(c, company_name)
        update_data = {'ats_discovery_attempted_at': datetime.utcnow()}
        if result:
            update_data['ats_type'], update_data['ats_slug'] = result
            logger.info(f"Discovered ATS for '{company_name}': {result[0]}/{result[1]}")
        await company_repo.update(company_id, update_data)
        return result

    if client is not None:
        return await _run(client)

    async with ATSClient() as c:
        return await _run(c)
