"""Hirist API HTTP client with rate limiting.

Undocumented endpoint (found via live network inspection, see config.py
docstring) — no auth required, size param honored well past the 50
the UI itself requests (tested up to 200).
"""

import logging
from typing import Dict, Any, Optional, List

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ...core.exceptions import ValidationError, ProcessingError
from .._common.rate_limiter import SimpleRateLimiter

logger = logging.getLogger(__name__)

HIRIST_SEARCH_URL = "https://gladiator.hirist.tech/job/search"
# The search endpoint returns no job description at all, which is why every
# Hirist row landed with an empty job_details.description. The detail endpoint
# does return it, as `data.introText` (HTML). Found the same way as the search
# endpoint: watching what the job page requests after hydration. No auth.
HIRIST_DETAIL_URL = "https://gladiator.hirist.tech/job/detail"
PAGE_SIZE = 200


class HiristAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class HiristPage:
    def __init__(self, data: Dict[str, Any]):
        self.jobs: List[Dict[str, Any]] = data.get('data', [])
        self.total_jobs: int = data.get('totalJobs', 0)
        self.has_more: bool = data.get('hasMore', False)


class HiristClient:
    def __init__(self, rate_limiter: Optional[SimpleRateLimiter] = None):
        self.rate_limiter = rate_limiter or SimpleRateLimiter('hirist', calls_per_window=2, window_seconds=1)
        self.client_config = {
            'timeout': httpx.Timeout(30.0),
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 JobRadar/1.0',
                'Accept': 'application/json',
                'Referer': 'https://www.hirist.tech/',
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
    async def _get(self, params: Dict[str, Any], url: str = HIRIST_SEARCH_URL) -> httpx.Response:
        response = await self.http_client.get(url, params=params)
        if response.status_code == 200:
            return response
        raise HiristAPIError(f"API error: {response.status_code}", status_code=response.status_code)

    async def fetch_page(self, query: str, page: int) -> HiristPage:
        """query is a keyword only — location text in the query does not filter (see config.py)."""
        async with self.rate_limiter:
            await self.rate_limiter.wait_if_needed("hirist_client")

        try:
            response = await self._get({'query': query, 'page': page, 'size': PAGE_SIZE})
        except HiristAPIError:
            raise
        except Exception as e:
            raise ProcessingError(f"Failed to fetch Hirist page (query='{query}', page={page}): {e}")

        try:
            data = response.json()
        except ValueError as e:
            raise ValidationError(f"Invalid JSON response: {e}")

        if 'data' not in data:
            raise ValidationError("Unexpected Hirist response shape: missing 'data'")

        logger.info(f"Fetched {len(data['data'])} jobs from Hirist (query='{query}', page={page})")
        return HiristPage(data)

    async def fetch_detail(self, job_code: str) -> Optional[Dict[str, Any]]:
        """Fetch one job's detail payload. Returns None when it has been taken
        down or the shape is unexpected — a missing description is never worth
        failing a backfill run over."""
        async with self.rate_limiter:
            await self.rate_limiter.wait_if_needed("hirist_client")

        try:
            response = await self._get({'jobcode': job_code}, url=HIRIST_DETAIL_URL)
        except HiristAPIError as e:
            if e.status_code in (400, 404, 410):
                return None
            raise
        except Exception as e:
            raise ProcessingError(f"Failed to fetch Hirist detail (jobcode={job_code}): {e}")

        try:
            data = response.json()
        except ValueError as e:
            raise ValidationError(f"Invalid JSON in Hirist detail response: {e}")

        payload = data.get('data')
        return payload if isinstance(payload, dict) else None

    async def health_check(self) -> bool:
        try:
            await self.fetch_page("python developer", 0)
            return True
        except Exception as e:
            logger.error(f"Hirist health check failed: {e}")
            return False


async def test_hirist_connection() -> bool:
    try:
        async with HiristClient() as client:
            return await client.health_check()
    except Exception as e:
        logger.error(f"Hirist connection test failed: {e}")
        return False
