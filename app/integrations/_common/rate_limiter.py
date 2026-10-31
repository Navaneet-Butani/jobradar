"""Shared rate limiter for source adapters — parameterized version of
InstahyreRateLimiter, reused instead of copy-pasted per source. Redis-backed
sliding window with an in-memory fallback if Redis is unavailable.
"""

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
    allowed: bool
    retry_after: Optional[float] = None
    current_count: int = 0
    limit: int = 1
    window_seconds: int = 1
    reset_time: Optional[float] = None


class SimpleRateLimiter:
    """Sliding-window rate limiter, keyed per source so instances don't collide in Redis."""

    def __init__(
        self,
        key_prefix: str,
        calls_per_window: int = 1,
        window_seconds: int = 1,
        redis_url: Optional[str] = None,
    ):
        self.key_prefix = f"{key_prefix}_rate_limit"
        self.calls_per_window = calls_per_window
        self.window_seconds = window_seconds
        self.redis_url = redis_url or settings.redis_url
        self.redis_client: Optional[redis.Redis] = None

        self._last_request_time = 0.0
        self._request_count = 0

    async def __aenter__(self):
        if not self.redis_url:  # no Redis configured: in-memory limiting
            self.redis_client = None
            return self
        try:
            self.redis_client = redis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True,
                socket_connect_timeout=2, socket_timeout=2,
            )
            await self.redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable for {self.key_prefix}, using in-memory rate limiting: {e}")
            self.redis_client = None
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.redis_client:
            await self.redis_client.close()

    async def acquire(self, identifier: str = "default") -> RateLimitStatus:
        current_time = time.time()
        if self.redis_client:
            return await self._acquire_redis(identifier, current_time)
        return self._acquire_memory(current_time)

    async def _acquire_redis(self, identifier: str, current_time: float) -> RateLimitStatus:
        key = f"{self.key_prefix}:{identifier}"
        try:
            pipeline = self.redis_client.pipeline()
            pipeline.zremrangebyscore(key, 0, current_time - self.window_seconds)
            pipeline.zcard(key)
            pipeline.zadd(key, {str(current_time): current_time})
            pipeline.expire(key, self.window_seconds + 1)
            results = await pipeline.execute()
            current_count = results[1]

            if current_count < self.calls_per_window:
                return RateLimitStatus(allowed=True, current_count=current_count + 1,
                                        limit=self.calls_per_window, window_seconds=self.window_seconds)

            await self.redis_client.zrem(key, str(current_time))
            oldest = await self.redis_client.zrange(key, 0, 0, withscores=True)
            retry_after = (oldest[0][1] + self.window_seconds - current_time) if oldest else self.window_seconds
            return RateLimitStatus(allowed=False, retry_after=max(0, retry_after), current_count=current_count,
                                    limit=self.calls_per_window, window_seconds=self.window_seconds,
                                    reset_time=current_time + retry_after)
        except Exception as e:
            logger.error(f"Redis rate limiting error for {self.key_prefix}, falling back to memory: {e}")
            return self._acquire_memory(current_time)

    def _acquire_memory(self, current_time: float) -> RateLimitStatus:
        if current_time - self._last_request_time >= self.window_seconds:
            self._request_count = 0
            self._last_request_time = current_time

        if self._request_count < self.calls_per_window:
            self._request_count += 1
            return RateLimitStatus(allowed=True, current_count=self._request_count,
                                    limit=self.calls_per_window, window_seconds=self.window_seconds)

        retry_after = self.window_seconds - (current_time - self._last_request_time)
        return RateLimitStatus(allowed=False, retry_after=max(0, retry_after), current_count=self._request_count,
                                limit=self.calls_per_window, window_seconds=self.window_seconds,
                                reset_time=current_time + retry_after)

    async def wait_if_needed(self, identifier: str = "default") -> RateLimitStatus:
        status = await self.acquire(identifier)
        if not status.allowed and status.retry_after:
            logger.info(f"{self.key_prefix} rate limit reached, waiting {status.retry_after:.2f}s")
            await asyncio.sleep(status.retry_after)
            return await self.acquire(identifier)
        return status
