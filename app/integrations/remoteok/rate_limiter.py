"""Rate limiter for RemoteOK API integration."""

import asyncio
import logging
import time
from typing import Optional
from dataclasses import dataclass

import redis.asyncio as redis
from ...config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class RateLimitStatus:
    """Status of rate limiting for RemoteOK API."""
    allowed: bool
    retry_after: Optional[float] = None
    current_count: int = 0
    limit: int = 1
    window_seconds: int = 1
    reset_time: Optional[float] = None


class RemoteOKRateLimiter:
    """Rate limiter for RemoteOK API (1 request per second)."""

    def __init__(self,
                 calls_per_window: int = 1,
                 window_seconds: int = 1,
                 redis_url: Optional[str] = None):
        """
        Initialize RemoteOK rate limiter.

        Args:
            calls_per_window: Number of calls allowed per window (default: 1)
            window_seconds: Window duration in seconds (default: 1)
            redis_url: Redis URL for distributed rate limiting
        """
        self.calls_per_window = calls_per_window
        self.window_seconds = window_seconds
        self.redis_url = redis_url or settings.redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.key_prefix = "remoteok_rate_limit"

        # Fallback to in-memory rate limiting if Redis is unavailable
        self._last_request_time = 0.0
        self._request_count = 0

    async def __aenter__(self):
        """Async context manager entry."""
        if not self.redis_url:  # no Redis configured: in-memory limiting
            self.redis_client = None
            return self
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            # Test connection
            await self.redis_client.ping()
            logger.debug("Connected to Redis for RemoteOK rate limiting")
        except Exception as e:
            logger.warning(f"Redis connection failed, using in-memory rate limiting: {e}")
            self.redis_client = None
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.redis_client:
            await self.redis_client.close()

    async def acquire(self, identifier: str = "default") -> RateLimitStatus:
        """
        Acquire permission for an API call.

        Args:
            identifier: Identifier for the rate limit (for multiple clients)

        Returns:
            RateLimitStatus with permission and timing info
        """
        current_time = time.time()

        if self.redis_client:
            return await self._acquire_redis(identifier, current_time)
        else:
            return await self._acquire_memory(current_time)

    async def _acquire_redis(self, identifier: str, current_time: float) -> RateLimitStatus:
        """Redis-based distributed rate limiting."""
        key = f"{self.key_prefix}:{identifier}"
        window_start = int(current_time) // self.window_seconds * self.window_seconds

        try:
            # Use Redis sliding window rate limiting
            pipeline = self.redis_client.pipeline()

            # Remove expired entries
            pipeline.zremrangebyscore(key, 0, current_time - self.window_seconds)

            # Count current requests in window
            pipeline.zcard(key)

            # Add current request
            pipeline.zadd(key, {str(current_time): current_time})

            # Set expiry
            pipeline.expire(key, self.window_seconds + 1)

            results = await pipeline.execute()
            current_count = results[1]

            if current_count < self.calls_per_window:
                return RateLimitStatus(
                    allowed=True,
                    current_count=current_count + 1,
                    limit=self.calls_per_window,
                    window_seconds=self.window_seconds
                )
            else:
                # Remove the request we just added since it's not allowed
                await self.redis_client.zrem(key, str(current_time))

                # Calculate when the next slot will be available
                oldest_scores = await self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest_scores:
                    oldest_time = oldest_scores[0][1]
                    retry_after = oldest_time + self.window_seconds - current_time
                else:
                    retry_after = self.window_seconds

                return RateLimitStatus(
                    allowed=False,
                    retry_after=max(0, retry_after),
                    current_count=current_count,
                    limit=self.calls_per_window,
                    window_seconds=self.window_seconds,
                    reset_time=current_time + retry_after
                )

        except Exception as e:
            logger.error(f"Redis rate limiting error, falling back to memory: {e}")
            return await self._acquire_memory(current_time)

    async def _acquire_memory(self, current_time: float) -> RateLimitStatus:
        """In-memory rate limiting fallback."""
        # Reset counter if window has passed
        if current_time - self._last_request_time >= self.window_seconds:
            self._request_count = 0
            self._last_request_time = current_time

        if self._request_count < self.calls_per_window:
            self._request_count += 1
            return RateLimitStatus(
                allowed=True,
                current_count=self._request_count,
                limit=self.calls_per_window,
                window_seconds=self.window_seconds
            )
        else:
            retry_after = self.window_seconds - (current_time - self._last_request_time)
            return RateLimitStatus(
                allowed=False,
                retry_after=max(0, retry_after),
                current_count=self._request_count,
                limit=self.calls_per_window,
                window_seconds=self.window_seconds,
                reset_time=current_time + retry_after
            )

    async def wait_if_needed(self, identifier: str = "default") -> RateLimitStatus:
        """
        Wait if rate limit would be exceeded, then acquire permission.

        Args:
            identifier: Identifier for the rate limit

        Returns:
            RateLimitStatus after successful acquisition
        """
        status = await self.acquire(identifier)

        if not status.allowed and status.retry_after:
            logger.info(f"Rate limit reached, waiting {status.retry_after:.2f} seconds")
            await asyncio.sleep(status.retry_after)
            # Try again after waiting
            return await self.acquire(identifier)

        return status

    async def get_status(self, identifier: str = "default") -> RateLimitStatus:
        """
        Get current rate limit status without making a request.

        Args:
            identifier: Identifier for the rate limit

        Returns:
            Current RateLimitStatus
        """
        current_time = time.time()

        if self.redis_client:
            try:
                key = f"{self.key_prefix}:{identifier}"

                # Clean expired entries and count current
                pipeline = self.redis_client.pipeline()
                pipeline.zremrangebyscore(key, 0, current_time - self.window_seconds)
                pipeline.zcard(key)
                results = await pipeline.execute()

                current_count = results[1]

                return RateLimitStatus(
                    allowed=current_count < self.calls_per_window,
                    current_count=current_count,
                    limit=self.calls_per_window,
                    window_seconds=self.window_seconds
                )

            except Exception as e:
                logger.error(f"Redis status check error: {e}")

        # Memory fallback
        if time.time() - self._last_request_time >= self.window_seconds:
            current_count = 0
        else:
            current_count = self._request_count

        return RateLimitStatus(
            allowed=current_count < self.calls_per_window,
            current_count=current_count,
            limit=self.calls_per_window,
            window_seconds=self.window_seconds
        )