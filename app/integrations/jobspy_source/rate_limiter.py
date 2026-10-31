"""LinkedIn run-frequency discipline for JobSpy.

Not a per-request rate limiter — JobSpy makes its own HTTP calls and
manages its own pacing. What matters here is how *often the whole scrape
runs*: LinkedIn rate-limits around page 10 without a proxy, and repeated
scraping is the fastest way to get blocked. docs/sources.md is
explicit: 2-3 runs/day maximum, never hourly.
"""

import logging
import time
from typing import Optional

import redis.asyncio as redis
from ...config.settings import settings

logger = logging.getLogger(__name__)

REDIS_KEY = "jobspy:linkedin:last_run"
ROTATION_KEY = "jobspy:linkedin:rotation_index"
MIN_SECONDS_BETWEEN_RUNS = 3 * 60 * 60  # 3 hours -> at most ~8/day ceiling; caller should aim for 2-3


class LinkedInRunTracker:
    """Tracks the last LinkedIn scrape time so callers can enforce the discipline."""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.redis_url
        self._memory_last_run: Optional[float] = None
        self._memory_rotation = 0

    async def seconds_since_last_run(self) -> Optional[float]:
        """None if there's no record of a previous run."""
        try:
            client = redis.from_url(self.redis_url, socket_connect_timeout=2, socket_timeout=2)
            last_run = await client.get(REDIS_KEY)
            await client.close()
            if last_run is not None:
                return time.time() - float(last_run)
        except Exception as e:
            logger.debug(f"Redis unavailable for LinkedIn run tracking, using in-memory: {e}")

        if self._memory_last_run is not None:
            return time.time() - self._memory_last_run
        return None

    async def can_run_now(self) -> bool:
        elapsed = await self.seconds_since_last_run()
        return elapsed is None or elapsed >= MIN_SECONDS_BETWEEN_RUNS

    async def record_run(self) -> None:
        now = time.time()
        self._memory_last_run = now
        try:
            client = redis.from_url(self.redis_url, socket_connect_timeout=2, socket_timeout=2)
            await client.set(REDIS_KEY, str(now))
            await client.close()
        except Exception as e:
            logger.debug(f"Redis unavailable for LinkedIn run tracking: {e}")

    async def next_rotation_offset(self, total: int, advance_by: int = 1) -> int:
        """
        Persisted round-robin offset into a priority-ordered search list, so each
        sweep's limited LinkedIn budget lands on a different (city, term) pair
        instead of always the first one in the list — without this, only the
        very first entry would ever get LinkedIn coverage, forever.
        """
        try:
            client = redis.from_url(self.redis_url, socket_connect_timeout=2, socket_timeout=2)
            new_total = await client.incrby(ROTATION_KEY, advance_by)  # atomic; new_total is post-increment
            await client.close()
            return (new_total - advance_by) % total
        except Exception as e:
            logger.debug(f"Redis unavailable for LinkedIn rotation, using in-memory: {e}")
            current = self._memory_rotation
            self._memory_rotation = (current + advance_by) % total
            return current % total
