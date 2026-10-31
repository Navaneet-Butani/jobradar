"""Ashby GraphQL job board fetch."""

import logging
from typing import Dict, Any, List

from .client import ATSClient, ATSAPIError

logger = logging.getLogger(__name__)

ASHBY_URL = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"

# Only fields that actually exist on JobPostingBriefsWithIdsAndTeamId — Ashby's
# GraphQL schema is stricter than docs/sources.mdexample query
# (jobUrl/applyUrl/teamNames/publishedDate/descriptionPlain all 400 on this type).
ASHBY_QUERY = (
    "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) { "
    "jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { "
    "jobPostings { id title locationName employmentType compensationTierSummary } } }"
)


async def fetch_ashby_jobs(client: ATSClient, slug: str, company_name: str) -> List[Dict[str, Any]]:
    """Fetch all open postings for a company's Ashby board.

    Returns [] if the slug doesn't exist (jobBoard is null) — that's a
    normal, expected outcome, not an error.
    """
    payload = {
        "operationName": "ApiJobBoardWithTeams",
        "variables": {"organizationHostedJobsPageName": slug},
        "query": ASHBY_QUERY,
    }

    response = await client.post_json(ASHBY_URL, payload, identifier="ashby")

    try:
        data = response.json()
    except ValueError:
        raise ATSAPIError(f"Invalid JSON from Ashby for '{slug}'")

    if data.get('errors'):
        raise ATSAPIError(f"Ashby GraphQL error for '{slug}': {data['errors']}")

    job_board = (data.get('data') or {}).get('jobBoard')
    if not job_board:
        return []

    jobs = job_board.get('jobPostings', [])
    for job in jobs:
        job['_company_name'] = company_name
        job['_apply_url'] = f"https://jobs.ashbyhq.com/{slug}/{job.get('id')}"
        job['_location'] = job.get('locationName')

    logger.info(f"Fetched {len(jobs)} Ashby jobs for '{slug}'")
    return jobs
