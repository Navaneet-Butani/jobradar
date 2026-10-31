"""RemoteOK API HTTP client with rate limiting and caching."""

import asyncio
import json
import logging
import time
from decimal import Decimal
from typing import Dict, Any, Optional, List
from urllib.parse import urljoin

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ...config.settings import settings
from ...core.exceptions import ValidationError, ProcessingError
from .rate_limiter import RemoteOKRateLimiter

logger = logging.getLogger(__name__)


class RemoteOKAPIError(Exception):
    """Base exception for RemoteOK API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}
        super().__init__(message)


class RemoteOKConnectionError(RemoteOKAPIError):
    """Raised when connection to RemoteOK API fails."""
    pass


class RemoteOKRateLimitError(RemoteOKAPIError):
    """Raised when rate limit is exceeded."""
    pass


class RemoteOKServerError(RemoteOKAPIError):
    """Raised when server returns 5xx errors."""
    pass


class RemoteOKResponse:
    """Wrapper for RemoteOK API responses with metadata."""

    def __init__(self, data: List[Dict[str, Any]], response_time_ms: float, cached: bool = False):
        self.data = data
        self.response_time_ms = response_time_ms
        self.cached = cached
        self.job_count = len(data) if data else 0
        self.timestamp = time.time()

    def is_valid(self) -> bool:
        """Check if response contains valid job data."""
        return self.data is not None and isinstance(self.data, list)

    def get_jobs(self) -> List[Dict[str, Any]]:
        """Get job listings from response."""
        if not self.is_valid():
            return []
        return self.data

    def get_stats(self) -> Dict[str, Any]:
        """Get response statistics."""
        return {
            'job_count': self.job_count,
            'response_time_ms': self.response_time_ms,
            'cached': self.cached,
            'timestamp': self.timestamp,
            'valid': self.is_valid()
        }


class RemoteOKClient:
    """HTTP client for RemoteOK API with rate limiting and caching."""

    def __init__(self,
                 base_url: Optional[str] = None,
                 rate_limiter: Optional[RemoteOKRateLimiter] = None,
                 cache_ttl: int = 3600):
        """
        Initialize RemoteOK client.

        Args:
            base_url: RemoteOK API base URL
            rate_limiter: Rate limiter instance
            cache_ttl: Cache TTL in seconds (default: 1 hour)
        """
        self.base_url = base_url or settings.remoteok_base_url
        self.rate_limiter = rate_limiter or RemoteOKRateLimiter()
        self.cache_ttl = cache_ttl
        self.timeout = 30.0
        self.max_retries = 3

        # In-memory cache for API responses
        self._cache: Dict[str, Dict[str, Any]] = {}

        # HTTP client configuration
        self.client_config = {
            'timeout': httpx.Timeout(self.timeout),
            'headers': {
                'User-Agent': 'Job Portal API Client/1.0',
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate'
            },
            'follow_redirects': True
        }

    async def __aenter__(self):
        """Async context manager entry."""
        self.http_client = httpx.AsyncClient(**self.client_config)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if hasattr(self, 'http_client'):
            await self.http_client.aclose()

    def _get_cache_key(self, endpoint: str) -> str:
        """Generate cache key for endpoint."""
        return f"remoteok:{endpoint}"

    def _is_cache_valid(self, cache_entry: Dict[str, Any]) -> bool:
        """Check if cache entry is still valid."""
        if not cache_entry:
            return False

        cached_at = cache_entry.get('cached_at', 0)
        return time.time() - cached_at < self.cache_ttl

    def _cache_response(self, endpoint: str, data: List[Dict[str, Any]], response_time_ms: float):
        """Cache API response."""
        cache_key = self._get_cache_key(endpoint)
        self._cache[cache_key] = {
            'data': data,
            'response_time_ms': response_time_ms,
            'cached_at': time.time()
        }

    def _get_cached_response(self, endpoint: str) -> Optional[RemoteOKResponse]:
        """Get cached response if valid."""
        cache_key = self._get_cache_key(endpoint)
        cache_entry = self._cache.get(cache_key)

        if self._is_cache_valid(cache_entry):
            return RemoteOKResponse(
                data=cache_entry['data'],
                response_time_ms=cache_entry['response_time_ms'],
                cached=True
            )

        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError))
    )
    async def _make_request(self, endpoint: str) -> httpx.Response:
        """Make HTTP request with retry logic."""
        url = urljoin(self.base_url, endpoint)

        logger.debug(f"Making RemoteOK API request to: {url}")
        start_time = time.time()

        try:
            response = await self.http_client.get(url)
            response_time_ms = (time.time() - start_time) * 1000

            logger.debug(f"RemoteOK API response: {response.status_code} in {response_time_ms:.2f}ms")

            # Handle different status codes
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                raise RemoteOKRateLimitError(
                    "Rate limit exceeded",
                    status_code=response.status_code,
                    response_data={'retry_after': response.headers.get('retry-after')}
                )
            elif response.status_code >= 500:
                raise RemoteOKServerError(
                    f"Server error: {response.status_code}",
                    status_code=response.status_code,
                    response_data={'status_code': response.status_code}
                )
            else:
                raise RemoteOKAPIError(
                    f"API error: {response.status_code}",
                    status_code=response.status_code,
                    response_data={'status_code': response.status_code}
                )

        except httpx.TimeoutException:
            logger.warning(f"Request timeout for {url}")
            raise RemoteOKConnectionError("Request timeout")
        except httpx.ConnectError:
            logger.warning(f"Connection error for {url}")
            raise RemoteOKConnectionError("Connection failed")
        except Exception as e:
            logger.error(f"Unexpected error making request to {url}: {e}")
            raise RemoteOKAPIError(f"Request failed: {e}")

    async def fetch_all_jobs(self) -> RemoteOKResponse:
        """
        Fetch all jobs from RemoteOK API.

        Returns:
            RemoteOKResponse with job data and metadata
        """
        endpoint = ""  # RemoteOK API root returns all jobs

        # Check cache first
        cached_response = self._get_cached_response(endpoint)
        if cached_response:
            logger.debug("Returning cached RemoteOK response")
            return cached_response

        # Rate limiting
        async with self.rate_limiter:
            rate_status = await self.rate_limiter.wait_if_needed("remoteok_client")

            if not rate_status.allowed:
                raise RemoteOKRateLimitError(
                    f"Rate limit exceeded. Retry after {rate_status.retry_after} seconds",
                    response_data={'retry_after': rate_status.retry_after}
                )

        start_time = time.time()

        try:
            response = await self._make_request(endpoint)
            response_time_ms = (time.time() - start_time) * 1000

            # Parse JSON response
            try:
                data = response.json()
                if not isinstance(data, list):
                    raise ValidationError("Expected JSON array from RemoteOK API")

                # Cache successful response
                self._cache_response(endpoint, data, response_time_ms)

                logger.info(f"Successfully fetched {len(data)} jobs from RemoteOK in {response_time_ms:.2f}ms")

                return RemoteOKResponse(data, response_time_ms, cached=False)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse RemoteOK JSON response: {e}")
                raise ValidationError(f"Invalid JSON response: {e}")

        except RemoteOKAPIError:
            # Re-raise API errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching RemoteOK jobs: {e}")
            raise ProcessingError(f"Failed to fetch jobs: {e}")

    async def health_check(self) -> bool:
        """
        Test basic connectivity to RemoteOK API.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            async with self.rate_limiter:
                rate_status = await self.rate_limiter.wait_if_needed("health_check")

                if not rate_status.allowed:
                    logger.warning("Health check skipped due to rate limiting")
                    return False

            response = await self._make_request("")
            return response.status_code == 200

        except Exception as e:
            logger.error(f"RemoteOK health check failed: {e}")
            return False

    async def get_api_stats(self) -> Dict[str, Any]:
        """
        Get API usage statistics.

        Returns:
            Dictionary with usage statistics
        """
        async with self.rate_limiter:
            rate_status = await self.rate_limiter.get_status("remoteok_client")

        return {
            'base_url': self.base_url,
            'cache_ttl': self.cache_ttl,
            'cached_endpoints': len(self._cache),
            'rate_limit': {
                'current_count': rate_status.current_count,
                'limit': rate_status.limit,
                'window_seconds': rate_status.window_seconds,
                'allowed': rate_status.allowed
            },
            'config': {
                'timeout': self.timeout,
                'max_retries': self.max_retries
            }
        }

    def clear_cache(self):
        """Clear response cache."""
        self._cache.clear()
        logger.info("RemoteOK API cache cleared")


async def test_remoteok_connection() -> bool:
    """Test connection to RemoteOK API."""
    try:
        async with RemoteOKClient() as client:
            return await client.health_check()
    except Exception as e:
        logger.error(f"RemoteOK connection test failed: {e}")
        return False