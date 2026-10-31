"""Himalayas API HTTP client with rate limiting. Offset/limit pagination."""

import logging
from typing import Dict, Any, Optional, List

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ...config.settings import settings
from ...core.exceptions import ValidationError, ProcessingError
from .._common.rate_limiter import SimpleRateLimiter

logger = logging.getLogger(__name__)

PAGE_LIMIT = 100  # requested; server caps at 20 regardless (verified live) — fetcher advances by actual count returned


class HimalayasAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class HimalayasPage:
    def __init__(self, data: Dict[str, Any]):
        self.jobs: List[Dict[str, Any]] = data.get('jobs', [])
        self.total_count: int = data.get('totalCount', 0)
        self.offset: int = data.get('offset', 0)


class HimalayasClient:
    def __init__(self, base_url: Optional[str] = None, rate_limiter: Optional[SimpleRateLimiter] = None):
        self.base_url = base_url or settings.himalayas_base_url
        self.rate_limiter = rate_limiter or SimpleRateLimiter('himalayas', calls_per_window=2, window_seconds=1)
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
    async def _get(self, params: Dict[str, Any]) -> httpx.Response:
        response = await self.http_client.get(self.base_url, params=params)
        if response.status_code == 200:
            return response
        raise HimalayasAPIError(f"API error: {response.status_code}", status_code=response.status_code)

    async def fetch_page(self, offset: int) -> HimalayasPage:
        async with self.rate_limiter:
            await self.rate_limiter.wait_if_needed("himalayas_client")

        try:
            response = await self._get({'offset': offset, 'limit': PAGE_LIMIT})
        except HimalayasAPIError:
            raise
        except Exception as e:
            raise ProcessingError(f"Failed to fetch Himalayas page (offset={offset}): {e}")

        try:
            data = response.json()
        except ValueError as e:
            raise ValidationError(f"Invalid JSON response: {e}")

        if 'jobs' not in data:
            raise ValidationError("Unexpected Himalayas response shape: missing 'jobs'")

        logger.info(f"Fetched {len(data['jobs'])} jobs from Himalayas (offset={offset})")
        return HimalayasPage(data)

    async def health_check(self) -> bool:
        try:
            await self.fetch_page(0)
            return True
        except Exception as e:
            logger.error(f"Himalayas health check failed: {e}")
            return False


async def test_himalayas_connection() -> bool:
    try:
        async with HimalayasClient() as client:
            return await client.health_check()
    except Exception as e:
        logger.error(f"Himalayas connection test failed: {e}")
        return False
