"""SmartRecruiters public postings API.

Used by many large employers with Indian offices (e.g. Bosch: 500+ India
postings). The list endpoint is filtered to India (`country=in`) because big
SmartRecruiters tenants post thousands of jobs worldwide. It has no
descriptions, so details are fetched only for titles that look like IT roles,
capped per company per run.
"""

import logging
from typing import Any, Dict, List

from .client import ATSAPIError, ATSClient, ATSNotFoundError
from ...services.role_filter import is_it_role

logger = logging.getLogger(__name__)

BASE = "https://api.smartrecruiters.com/v1/companies"
PAGE_SIZE = 100
MAX_PAGES = 10
# ponytail: fixed per-run cap, so a large tenant gets descriptions for its first 40
# IT postings only; add SmartRecruiters to backfill_descriptions if that matters.
DETAIL_LIMIT = 40  # detail requests per company per run


def _iso(value) -> str | None:
    return value[:19] if isinstance(value, str) and len(value) >= 19 else None


async def fetch_smartrecruiters_jobs(client: ATSClient, slug: str, company_name: str) -> List[Dict[str, Any]]:
    postings: List[Dict[str, Any]] = []
    for page in range(MAX_PAGES):
        try:
            response = await client.get(
                f"{BASE}/{slug}/postings?country=in&limit={PAGE_SIZE}&offset={page * PAGE_SIZE}",
                identifier="smartrecruiters",
            )
            data = response.json()
        except ATSNotFoundError:
            return []
        except ValueError:
            raise ATSAPIError(f"Invalid JSON from SmartRecruiters for '{slug}'")
        content = data.get("content") or []
        postings.extend(content)
        if len(content) < PAGE_SIZE or len(postings) >= (data.get("totalFound") or 0):
            break

    details = 0
    for job in postings:
        location = job.get("location") or {}
        job["title"] = job.get("name")
        job["_company_name"] = company_name
        job["_location"] = ", ".join(filter(None, [
            location.get("city"), location.get("region"), "India", "Remote" if location.get("remote") else None,
        ]))
        job["_posted_date"] = _iso(job.get("releasedDate"))
        job["_apply_url"] = f"https://jobs.smartrecruiters.com/{slug}/{job.get('id')}"
        if details < DETAIL_LIMIT and is_it_role(job["title"] or ""):
            details += 1
            try:
                detail = (await client.get(f"{BASE}/{slug}/postings/{job.get('id')}", identifier="smartrecruiters")).json()
                sections = (detail.get("jobAd") or {}).get("sections") or {}
                job["description"] = "\n".join(
                    (sections.get(k) or {}).get("text") or "" for k in ("jobDescription", "qualifications")
                ).strip() or None
                job["_apply_url"] = detail.get("applyUrl") or detail.get("postingUrl") or job["_apply_url"]
            except (ATSAPIError, ValueError) as e:
                logger.debug(f"SmartRecruiters detail failed for {slug}/{job.get('id')}: {e}")

    logger.info(f"Fetched {len(postings)} SmartRecruiters India jobs for '{slug}' ({details} with details)")
    return postings


async def board_company_name(client: ATSClient, slug: str) -> str | None:
    """The tenant's display name if it has any India postings (used by discovery)."""
    try:
        data = (await client.get(f"{BASE}/{slug}/postings?country=in&limit=1", identifier="smartrecruiters")).json()
    except (ATSAPIError, ValueError):
        return None
    content = data.get("content") or []
    return ((content[0].get("company") or {}).get("name") if content else None) or None
