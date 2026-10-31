"""LinkedIn guest-endpoint HTTP client.

These are the public endpoints LinkedIn serves to logged-out visitors and
search-engine crawlers. **No login, no cookies, no account is involved** —
which is the whole point: the alternative libraries all want an authenticated
session, and that puts a real account at ban risk to reach the same data.

Job posts only. Never people, never profiles (CLAUDE.md non-goal).

Measured 2026-08-18 from a residential IP, recorded in docs/sources.md:
  * the search endpoint returns **10 cards per response**, not the 25 every
    blog claims — and JobSpy's own scraper steps `start` by 25, silently
    skipping ~60% of every result set. Hence PAGE_STEP = 10.
  * `start=990` still answers 200; `start=1000` is a hard HTTP 400. So one
    query yields at most ~1,000 jobs and volume comes from splitting the
    query (keyword x location x time window), not from paging harder.
  * no 429 across ~130 requests at ~3s spacing. That was one IP on one day;
    a shared CI runner may be treated very differently, so the fetcher
    treats 429 as a stop signal rather than something to retry through.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ...core.exceptions import ProcessingError
from .._common.rate_limiter import SimpleRateLimiter

logger = logging.getLogger(__name__)

LINKEDIN_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LINKEDIN_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"

PAGE_STEP = 10      # cards per response, measured — see module docstring
MAX_START = 1000    # start=1000 is a hard 400

_JOB_ID_PATTERN = re.compile(r"(\d{6,})")


class LinkedInBlockedError(Exception):
    """429 or an equivalent block. Always stop the run; never retry through it."""


class LinkedInClient:
    def __init__(self, rate_limiter: Optional[SimpleRateLimiter] = None):
        # One request per 3 seconds. Deliberately slower than every other
        # adapter here: this is the one source that will quietly blocklist an
        # IP, and we have no proxy pool to fall back on.
        self.rate_limiter = rate_limiter or SimpleRateLimiter(
            'linkedin', calls_per_window=1, window_seconds=3
        )
        self.client_config = {
            'timeout': httpx.Timeout(20.0),
            'headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
                ),
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            'follow_redirects': True,
        }

    async def __aenter__(self):
        self.http_client = httpx.AsyncClient(**self.client_config)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'http_client'):
            await self.http_client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    )
    async def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        response = await self.http_client.get(url, params=params)
        if response.status_code == 429:
            raise LinkedInBlockedError("429 from LinkedIn — stopping this run")
        return response

    async def search_page(
        self,
        keywords: str,
        location: str,
        start: int,
        *,
        seconds_old: Optional[int] = None,
        remote_only: bool = False,
    ) -> Optional[List[Dict[str, Any]]]:
        """One page of results. None means "stop paging this query".

        None covers both the end of the result set (400 past the cap, or an
        empty page) and a takedown; the caller does not need to tell them
        apart, it just moves to the next query.
        """
        params: Dict[str, Any] = {"keywords": keywords, "location": location, "start": start}
        if seconds_old:
            params["f_TPR"] = f"r{seconds_old}"
        if remote_only:
            params["f_WT"] = 2

        async with self.rate_limiter:
            await self.rate_limiter.wait_if_needed("linkedin_client")

        try:
            response = await self._get(LINKEDIN_SEARCH_URL, params)
        except LinkedInBlockedError:
            raise
        except Exception as e:
            raise ProcessingError(f"LinkedIn search failed (keywords='{keywords}', start={start}): {e}")

        if response.status_code == 400:
            return None                      # past the ~1,000 cap
        if response.status_code != 200:
            logger.warning(f"LinkedIn search returned {response.status_code} at start={start}")
            return None

        cards = _parse_cards(response.text)
        return cards or None

    async def fetch_description(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Description + the job-criteria block for one posting, or None.

        Costs one request per job, so this is backfill work, never part of the
        bulk sweep.
        """
        async with self.rate_limiter:
            await self.rate_limiter.wait_if_needed("linkedin_client")

        try:
            response = await self._get(f"{LINKEDIN_DETAIL_URL}/{job_id}")
        except LinkedInBlockedError:
            raise
        except Exception as e:
            raise ProcessingError(f"LinkedIn detail failed (job_id={job_id}): {e}")

        if response.status_code != 200:
            return None
        return _parse_detail(response.text)


def _text(node) -> Optional[str]:
    return node.get_text(" ", strip=True) if node else None


def _parse_cards(html: str) -> List[Dict[str, Any]]:
    """Parse the guest search response into one dict per job card.

    The response is an HTML fragment, not JSON, so what gets stored as
    `raw_data` is this parsed dict rather than the markup — keeping the raw
    HTML would cost ~6 KB per job for markup we can always re-derive.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: List[Dict[str, Any]] = []

    for card in soup.find_all("div", class_="base-search-card"):
        link = card.find("a", class_="base-card__full-link")
        href = link["href"].split("?")[0] if link and link.get("href") else None
        if not href:
            continue

        match = _JOB_ID_PATTERN.search(href.rsplit("-", 1)[-1])
        if not match:
            continue

        company_link = card.find("a", class_="hidden-nested-link")
        time_tag = card.find("time")
        logo = card.find("img", class_="artdeco-entity-image")

        jobs.append({
            "job_id": match.group(1),
            "title": _text(card.find("h3", class_="base-search-card__title")),
            "company": _text(company_link) or _text(card.find("h4", class_="base-search-card__subtitle")),
            "company_url": company_link["href"].split("?")[0] if company_link and company_link.get("href") else None,
            "location": _text(card.find("span", class_="job-search-card__location")),
            "salary": _text(card.find("span", class_="job-search-card__salary-info")),
            "posted_at": time_tag.get("datetime") if time_tag else None,
            "posted_text": _text(time_tag),
            "job_url": href,
            "company_logo": logo.get("data-delayed-url") or logo.get("src") if logo else None,
            "fetched_at": datetime.utcnow().isoformat(),
        })

    return jobs


def _parse_detail(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    description = soup.find("div", class_="show-more-less-html__markup")

    criteria: Dict[str, str] = {}
    for item in soup.find_all("li", class_="description__job-criteria-item"):
        label = _text(item.find("h3"))
        value = _text(item.find("span"))
        if label and value:
            criteria[label.lower().replace(" ", "_")] = value

    return {
        "description_html": str(description) if description else None,
        "description_text": _text(description),
        "criteria": criteria,
    }


async def test_linkedin_connection() -> bool:
    try:
        async with LinkedInClient() as client:
            cards = await client.search_page("python developer", "India", 0)
            return bool(cards)
    except Exception as e:
        logger.error(f"LinkedIn connection test failed: {e}")
        return False
