"""Instahyre API HTTP client with rate limiting."""

import logging
import time
from typing import Dict, Any, Optional, List

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ...config.settings import settings
from ...core.exceptions import ValidationError, ProcessingError
from .rate_limiter import InstahyreRateLimiter

logger = logging.getLogger(__name__)

PAGE_LIMIT = 35  # server-side cap regardless of what's requested


class InstahyreAPIError(Exception):
    """Base exception for Instahyre API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}
        super().__init__(message)


class InstahyreConnectionError(InstahyreAPIError):
    """Raised when connection to Instahyre API fails."""
    pass


class InstahyreRateLimitError(InstahyreAPIError):
    """Raised when rate limit is exceeded."""
    pass


class InstahyreServerError(InstahyreAPIError):
    """Raised when server returns 5xx errors."""
    pass


class InstahyrePage:
    """One page of the Instahyre job_search response."""

    def __init__(self, data: Dict[str, Any], response_time_ms: float):
        self.data = data
        self.response_time_ms = response_time_ms
        self.objects: List[Dict[str, Any]] = data.get('objects', [])
        self.total_count: int = data.get('meta', {}).get('total_count', 0)
        self.offset: int = data.get('meta', {}).get('offset', 0)


class InstahyreClient:
    """HTTP client for the Instahyre job_search API."""

    def __init__(self,
                 base_url: Optional[str] = None,
                 rate_limiter: Optional[InstahyreRateLimiter] = None):
        self.base_url = base_url or settings.instahyre_base_url
        self.rate_limiter = rate_limiter or InstahyreRateLimiter(
            calls_per_window=settings.instahyre_rate_limit_calls,
            window_seconds=settings.instahyre_rate_limit_window
        )
        self.timeout = 30.0

        self.client_config = {
            'timeout': httpx.Timeout(self.timeout),
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 JobRadar/1.0',
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate'
            },
            'follow_redirects': True
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
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError))
    )
    async def _make_request(self, offset: int) -> httpx.Response:
        """Make HTTP request with retry logic."""
        params = {'job_type': 1, 'limit': PAGE_LIMIT, 'offset': offset}

        logger.debug(f"Making Instahyre API request: offset={offset}")
        start_time = time.time()

        try:
            response = await self.http_client.get(self.base_url, params=params)
            response_time_ms = (time.time() - start_time) * 1000
            logger.debug(f"Instahyre API response: {response.status_code} in {response_time_ms:.2f}ms")

            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                raise InstahyreRateLimitError(
                    "Rate limit exceeded",
                    status_code=response.status_code,
                    response_data={'retry_after': response.headers.get('retry-after')}
                )
            elif response.status_code >= 500:
                raise InstahyreServerError(
                    f"Server error: {response.status_code}",
                    status_code=response.status_code
                )
            else:
                raise InstahyreAPIError(
                    f"API error: {response.status_code}",
                    status_code=response.status_code
                )

        except httpx.TimeoutException:
            logger.warning(f"Request timeout at offset {offset}")
            raise InstahyreConnectionError("Request timeout")
        except httpx.ConnectError:
            logger.warning(f"Connection error at offset {offset}")
            raise InstahyreConnectionError("Connection failed")

    async def fetch_page(self, offset: int) -> InstahyrePage:
        """Fetch one page of job_search results."""
        async with self.rate_limiter:
            rate_status = await self.rate_limiter.wait_if_needed("instahyre_client")
            if not rate_status.allowed:
                raise InstahyreRateLimitError(
                    f"Rate limit exceeded. Retry after {rate_status.retry_after} seconds"
                )

        start_time = time.time()

        try:
            response = await self._make_request(offset)
            response_time_ms = (time.time() - start_time) * 1000

            try:
                data = response.json()
            except ValueError as e:
                raise ValidationError(f"Invalid JSON response: {e}")

            if 'objects' not in data:
                raise ValidationError("Unexpected Instahyre response shape: missing 'objects'")

            logger.info(f"Fetched {len(data['objects'])} jobs from Instahyre (offset={offset}) in {response_time_ms:.2f}ms")
            return InstahyrePage(data, response_time_ms)

        except InstahyreAPIError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching Instahyre page (offset={offset}): {e}")
            raise ProcessingError(f"Failed to fetch page: {e}")

    async def health_check(self) -> bool:
        """Test basic connectivity to the Instahyre API."""
        try:
            await self.fetch_page(0)
            return True
        except Exception as e:
            logger.error(f"Instahyre health check failed: {e}")
            return False


async def test_instahyre_connection() -> bool:
    """Test connection to the Instahyre API."""
    try:
        async with InstahyreClient() as client:
            return await client.health_check()
    except Exception as e:
        logger.error(f"Instahyre connection test failed: {e}")
        return False
