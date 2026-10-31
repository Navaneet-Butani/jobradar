"""Shared HTTP client for ATS (Greenhouse/Lever/Ashby) integrations."""

import logging
import time
from typing import Dict, Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .rate_limiter import ATSRateLimiter

logger = logging.getLogger(__name__)


class ATSAPIError(Exception):
    """Base exception for ATS API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ATSConnectionError(ATSAPIError):
    """Raised when connection to an ATS API fails."""
    pass


class ATSNotFoundError(ATSAPIError):
    """Raised when a company slug doesn't exist on this ATS."""
    pass


class ATSClient:
    """Shared HTTP client — one instance covers Greenhouse, Lever, and Ashby."""

    def __init__(self, rate_limiter: Optional[ATSRateLimiter] = None):
        self.rate_limiter = rate_limiter or ATSRateLimiter()
        self.timeout = 20.0
        self.client_config = {
            'timeout': httpx.Timeout(self.timeout),
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 JobRadar/1.0',
                'Accept': 'application/json',
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
    async def get(self, url: str, identifier: str) -> httpx.Response:
        """GET with rate limiting, retry, and 404-as-not-found handling."""
        async with self.rate_limiter:
            await self.rate_limiter.wait_if_needed(identifier)

        start_time = time.time()
        try:
            response = await self.http_client.get(url)
            logger.debug(f"ATS GET {url}: {response.status_code} in {(time.time() - start_time) * 1000:.0f}ms")

            if response.status_code == 200:
                return response
            elif response.status_code == 404:
                raise ATSNotFoundError(f"Not found: {url}", status_code=404)
            elif response.status_code == 429:
                raise ATSAPIError(f"Rate limited: {url}", status_code=429)
            else:
                raise ATSAPIError(f"Unexpected status {response.status_code}: {url}", status_code=response.status_code)

        except httpx.TimeoutException:
            raise ATSConnectionError(f"Request timeout: {url}")
        except httpx.ConnectError:
            raise ATSConnectionError(f"Connection failed: {url}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError))
    )
    async def post_json(self, url: str, payload: Dict[str, Any], identifier: str) -> httpx.Response:
        """POST JSON with rate limiting and retry (used by Ashby's GraphQL endpoint)."""
        async with self.rate_limiter:
            await self.rate_limiter.wait_if_needed(identifier)

        start_time = time.time()
        try:
            response = await self.http_client.post(url, json=payload)
            logger.debug(f"ATS POST {url}: {response.status_code} in {(time.time() - start_time) * 1000:.0f}ms")

            if response.status_code == 200:
                return response
            elif response.status_code == 404:
                raise ATSNotFoundError(f"Not found: {url}", status_code=404)
            elif response.status_code == 429:
                raise ATSAPIError(f"Rate limited: {url}", status_code=429)
            else:
                raise ATSAPIError(f"Unexpected status {response.status_code}: {url}", status_code=response.status_code)

        except httpx.TimeoutException:
            raise ATSConnectionError(f"Request timeout: {url}")
        except httpx.ConnectError:
            raise ATSConnectionError(f"Connection failed: {url}")
