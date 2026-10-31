"""Redis-based bloom filter for duplicate detection optimization."""

import logging
import hashlib
from typing import List, Optional
from datetime import datetime, timedelta

try:
    from redisbloom.client import Client as BloomClient
except ImportError:
    BloomClient = None

from ...core.redis import get_redis_client
from ...config.deduplication_config import get_dedup_config

logger = logging.getLogger(__name__)


class DuplicationBloomFilter:
    """
    Bloom filter for fast negative duplicate checks.

    Features:
    - 1M capacity with 0.001 false positive rate
    - Monthly reset to prevent false positive accumulation
    - Multiple hash functions for better distribution
    - Automatic statistics tracking
    - Graceful fallback when RedisBloom is not available
    """

    def __init__(self, redis_client=None, environment: str = "development"):
        self.redis = redis_client or get_redis_client()
        self.config = get_dedup_config(environment)
        self.bloom_config = self.config.bloom_filter

        # Check if RedisBloom is available
        self.bloom_available = BloomClient is not None

        if self.bloom_available:
            try:
                self.bloom_client = BloomClient(
                    host=self.redis.connection_pool.connection_kwargs.get('host', 'localhost'),
                    port=self.redis.connection_pool.connection_kwargs.get('port', 6379),
                    db=self.redis.connection_pool.connection_kwargs.get('db', 0)
                )
            except Exception as e:
                logger.warning(f"Failed to initialize BloomClient: {e}")
                self.bloom_available = False
                self.bloom_client = None
        else:
            logger.warning("redis-py-bloom not installed, falling back to Redis sets")
            self.bloom_client = None

        # Configuration
        self.filter_name = "job_dedup_bloom"
        self.fallback_set_name = "job_dedup_set"
        self.capacity = self.bloom_config['capacity']
        self.error_rate = self.bloom_config['error_rate']

        # Statistics tracking
        self.stats_key = "bloom_filter_stats"

    async def initialize(self) -> bool:
        """Initialize bloom filter with optimal parameters."""
        try:
            if self.bloom_available and self.bloom_client:
                # Check if filter exists
                exists = await self._filter_exists()

                if not exists:
                    # Create new bloom filter
                    success = self.bloom_client.bfCreate(
                        self.filter_name,
                        self.error_rate,
                        self.capacity
                    )

                    if success:
                        await self._update_stats(action='created')
                        logger.info(f"Created bloom filter: {self.filter_name}")
                    else:
                        logger.error("Failed to create bloom filter")
                        return False

                # Check if reset is needed (monthly)
                if await self._needs_reset():
                    await self.reset_filter()

                logger.info("Bloom filter initialized successfully")
            else:
                # Fallback to Redis set
                logger.info("Using Redis set fallback for bloom filter functionality")
                await self._update_stats(action='created')

            return True

        except Exception as e:
            logger.error(f"Error initializing bloom filter: {e}")
            return False

    def _no_backend(self) -> bool:
        """No RedisBloom and no Redis: run without the filter (every check goes to the DB)."""
        return not (self.bloom_available and self.bloom_client) and self.redis is None

    async def add_hash(self, content_hash: str) -> bool:
        """Add content hash to bloom filter."""
        try:
            if self._no_backend():
                return False
            if self.bloom_available and self.bloom_client:
                # Add to bloom filter
                result = self.bloom_client.bfAdd(self.filter_name, content_hash)
            else:
                # Fallback to Redis set
                result = await self.redis.sadd(self.fallback_set_name, content_hash)

                # Maintain set size (keep only recent entries)
                set_size = await self.redis.scard(self.fallback_set_name)
                if set_size > self.capacity:
                    # Remove random elements to maintain size
                    await self.redis.spop(self.fallback_set_name, set_size - self.capacity)

            # Update statistics
            await self._update_stats(action='add')

            logger.debug(f"Added hash to bloom filter: {content_hash[:12]}...")
            return bool(result)

        except Exception as e:
            logger.error(f"Error adding hash to bloom filter: {e}")
            return False

    async def check_hash(self, content_hash: str) -> bool:
        """
        Check if hash might exist in bloom filter.

        Returns:
            True: Hash might exist (requires database check)
            False: Hash definitely doesn't exist (skip database check)
        """
        try:
            if self._no_backend():
                return True
            if self.bloom_available and self.bloom_client:
                # Check bloom filter
                exists = self.bloom_client.bfExists(self.filter_name, content_hash)
            else:
                # Fallback to Redis set
                exists = await self.redis.sismember(self.fallback_set_name, content_hash)

            # Update statistics
            await self._update_stats(action='check', hit=exists)

            logger.debug(f"Bloom filter check for {content_hash[:12]}...: {exists}")
            return bool(exists)

        except Exception as e:
            logger.error(f"Error checking bloom filter: {e}")
            # Return True on error to be safe (fall back to database check)
            return True

    async def add_multiple_hashes(self, content_hashes: List[str]) -> int:
        """Add multiple hashes efficiently."""
        try:
            if self._no_backend():
                return 0
            added_count = 0

            if self.bloom_available and self.bloom_client:
                # Batch add to bloom filter
                for hash_value in content_hashes:
                    if self.bloom_client.bfAdd(self.filter_name, hash_value):
                        added_count += 1
            else:
                # Fallback to Redis set
                if content_hashes:
                    result = await self.redis.sadd(self.fallback_set_name, *content_hashes)
                    added_count = result

                    # Maintain set size
                    set_size = await self.redis.scard(self.fallback_set_name)
                    if set_size > self.capacity:
                        await self.redis.spop(self.fallback_set_name, set_size - self.capacity)

            # Update statistics
            await self._update_stats(action='batch_add', count=added_count)

            logger.info(f"Added {added_count} hashes to bloom filter")
            return added_count

        except Exception as e:
            logger.error(f"Error adding multiple hashes: {e}")
            return 0

    async def get_statistics(self) -> dict:
        """Get bloom filter statistics."""
        try:
            stats = {}

            if self.bloom_available and self.bloom_client:
                try:
                    # Get filter info from RedisBloom
                    info = self.bloom_client.bfInfo(self.filter_name)
                    stats.update({
                        'capacity': info.get('Capacity', 0),
                        'size': info.get('Size', 0),
                        'number_of_filters': info.get('Number of filters', 0),
                        'number_of_items_inserted': info.get('Number of items inserted', 0),
                        'expansion_rate': info.get('Expansion rate', 0),
                    })
                except Exception as e:
                    logger.warning(f"Could not get bloom filter info: {e}")
            else:
                # Fallback statistics from Redis set
                try:
                    set_size = await self.redis.scard(self.fallback_set_name)
                    stats.update({
                        'capacity': self.capacity,
                        'size': set_size,
                        'number_of_filters': 1,
                        'number_of_items_inserted': set_size,
                        'expansion_rate': 0,
                    })
                except Exception as e:
                    logger.warning(f"Could not get set statistics: {e}")

            # Get custom statistics
            custom_stats = await self.redis.hgetall(self.stats_key)
            stats.update({
                'total_adds': int(custom_stats.get('total_adds', 0)),
                'total_checks': int(custom_stats.get('total_checks', 0)),
                'total_hits': int(custom_stats.get('total_hits', 0)),
                'hit_rate': self._calculate_hit_rate(custom_stats),
                'created_at': custom_stats.get('created_at'),
                'last_reset': custom_stats.get('last_reset'),
                'implementation': 'RedisBloom' if self.bloom_available else 'Redis Set Fallback'
            })

            return stats

        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}

    async def reset_filter(self) -> bool:
        """Reset bloom filter (monthly maintenance)."""
        try:
            if self.bloom_available and self.bloom_client:
                # Delete existing filter
                try:
                    deleted = self.bloom_client.delete(self.filter_name)
                except:
                    deleted = True  # Assume success if delete fails

                if deleted:
                    # Create new filter
                    success = self.bloom_client.bfCreate(
                        self.filter_name,
                        self.error_rate,
                        self.capacity
                    )

                    if success:
                        await self._update_stats(action='reset')
                        logger.info("Bloom filter reset successfully")
                        return True
            else:
                # Fallback: clear Redis set
                await self.redis.delete(self.fallback_set_name)
                await self._update_stats(action='reset')
                logger.info("Bloom filter (Redis set) reset successfully")
                return True

            logger.error("Failed to reset bloom filter")
            return False

        except Exception as e:
            logger.error(f"Error resetting bloom filter: {e}")
            return False

    async def warm_filter(self, recent_hashes: List[str]) -> int:
        """Warm bloom filter with recent job hashes."""
        try:
            logger.info(f"Warming bloom filter with {len(recent_hashes)} hashes")

            added_count = await self.add_multiple_hashes(recent_hashes)

            await self._update_stats(action='warm', count=added_count)

            logger.info(f"Bloom filter warmed with {added_count} hashes")
            return added_count

        except Exception as e:
            logger.error(f"Error warming bloom filter: {e}")
            return 0

    # Private helper methods

    async def _filter_exists(self) -> bool:
        """Check if bloom filter exists."""
        if not self.bloom_available or not self.bloom_client:
            # Check if fallback set exists
            try:
                return await self.redis.exists(self.fallback_set_name) > 0
            except:
                return False

        try:
            self.bloom_client.bfInfo(self.filter_name)
            return True
        except:
            return False

    async def _needs_reset(self) -> bool:
        """Check if filter needs monthly reset."""
        try:
            stats = await self.redis.hgetall(self.stats_key)
            last_reset = stats.get('last_reset')

            if not last_reset:
                return False

            # Parse last reset date
            last_reset_date = datetime.fromisoformat(last_reset)

            # Check if more than 30 days ago
            return datetime.utcnow() - last_reset_date > timedelta(days=self.bloom_config['reset_interval_days'])

        except Exception:
            return False

    async def _update_stats(self, action: str, hit: bool = False, count: int = 1):
        """Update bloom filter statistics."""
        if self.redis is None:
            return
        try:
            current_time = datetime.utcnow().isoformat()

            # Use pipeline for atomic updates
            async with self.redis.pipeline() as pipeline:
                if action == 'created':
                    pipeline.hset(self.stats_key, 'created_at', current_time)
                    pipeline.hset(self.stats_key, 'last_reset', current_time)

                elif action == 'add':
                    pipeline.hincrby(self.stats_key, 'total_adds', 1)

                elif action == 'batch_add':
                    pipeline.hincrby(self.stats_key, 'total_adds', count)

                elif action == 'check':
                    pipeline.hincrby(self.stats_key, 'total_checks', 1)
                    if hit:
                        pipeline.hincrby(self.stats_key, 'total_hits', 1)

                elif action == 'reset':
                    pipeline.hset(self.stats_key, 'last_reset', current_time)
                    pipeline.hset(self.stats_key, 'total_adds', 0)
                    pipeline.hset(self.stats_key, 'total_checks', 0)
                    pipeline.hset(self.stats_key, 'total_hits', 0)

                elif action == 'warm':
                    pipeline.hincrby(self.stats_key, 'total_adds', count)
                    pipeline.hset(self.stats_key, 'last_warm', current_time)

                await pipeline.execute()

        except Exception as e:
            logger.error(f"Error updating statistics: {e}")

    def _calculate_hit_rate(self, stats: dict) -> float:
        """Calculate bloom filter hit rate."""
        try:
            total_checks = int(stats.get('total_checks', 0))
            total_hits = int(stats.get('total_hits', 0))

            if total_checks == 0:
                return 0.0

            return round(total_hits / total_checks, 3)

        except Exception:
            return 0.0