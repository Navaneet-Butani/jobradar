"""Remotive API HTTP client with rate limiting.

No pagination in the public API — a single request returns the full
current corpus (small: ~14-50 jobs at time of writing).
"""

import logging
from typing import Dict, Any, Optional, List

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ...config.settings import settings
from ...core.exceptions import ValidationError, ProcessingError
from .._common.rate_limiter import SimpleRateLimiter

logger = logging.getLogger(__name__)


class RemotiveAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class RemotivePage:
    def __init__(self, data: Dict[str, Any]):
        self.jobs: List[Dict[str, Any]] = data.get('jobs', [])
        self.total_count: int = data.get('total-job-count', len(self.jobs))


class RemotiveClient:
    def __init__(self, base_url: Optional[str] = None, rate_limiter: Optional[SimpleRateLimiter] = None):
        self.base_url = base_url or settings.remotive_base_url
        self.rate_limiter = rate_limiter or SimpleRateLimiter('remotive', calls_per_window=2, window_seconds=1)
        self.client_config = {
            'timeout': httpx.Timeout(30.0),
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 JobRadar/1.0',
                'Accept': 'application/json',
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
    async def _get(self, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        response = await self.http_client.get(self.base_url, params=params)
        if response.status_code == 200:
            return response
        raise RemotiveAPIError(f"API error: {response.status_code}", status_code=response.status_code)

    async def fetch_all(self) -> RemotivePage:
        async with self.rate_limiter:
            await self.rate_limiter.wait_if_needed("remotive_client")

        try:
            response = await self._get()
        except RemotiveAPIError:
            raise
        except Exception as e:
            raise ProcessingError(f"Failed to fetch Remotive jobs: {e}")

        try:
            data = response.json()
        except ValueError as e:
            raise ValidationError(f"Invalid JSON response: {e}")

        if 'jobs' not in data:
            raise ValidationError("Unexpected Remotive response shape: missing 'jobs'")

        logger.info(f"Fetched {len(data['jobs'])} jobs from Remotive")
        return RemotivePage(data)

    async def health_check(self) -> bool:
        try:
            await self.fetch_all()
            return True
        except Exception as e:
            logger.error(f"Remotive health check failed: {e}")
            return False


async def test_remotive_connection() -> bool:
    try:
        async with RemotiveClient() as client:
            return await client.health_check()
    except Exception as e:
        logger.error(f"Remotive connection test failed: {e}")
        return False
