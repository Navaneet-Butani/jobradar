"""Memory management for efficient batch processing."""

import logging
import gc
import weakref
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MemoryStats:
    current_mb: float
    peak_mb: float
    cache_size: int
    gc_collections: int


class DeduplicationMemoryManager:
    """Manages memory usage during deduplication processing."""

    def __init__(self, max_memory_mb: int = 500):
        self.max_memory_mb = max_memory_mb
        self.cache = {}
        self.weak_refs = weakref.WeakValueDictionary()
        self._cleanup_threshold = max_memory_mb * 0.8  # Clean up at 80% of limit

    async def check_memory_usage(self) -> MemoryStats:
        """Check current memory usage."""
        try:
            import psutil
            import os

            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()

            peak_mb = 0
            try:
                # Windows
                if hasattr(memory_info, 'peak_wset'):
                    peak_mb = memory_info.peak_wset / 1024 / 1024
                # Linux
                elif hasattr(memory_info, 'peak_vms'):
                    peak_mb = memory_info.peak_vms / 1024 / 1024
            except AttributeError:
                peak_mb = memory_info.rss / 1024 / 1024

            return MemoryStats(
                current_mb=memory_info.rss / 1024 / 1024,
                peak_mb=peak_mb,
                cache_size=len(self.cache),
                gc_collections=sum(gc.get_stats()[i]['collections'] for i in range(len(gc.get_stats())))
            )
        except ImportError:
            # Fallback when psutil is not available
            return MemoryStats(
                current_mb=0.0,
                peak_mb=0.0,
                cache_size=len(self.cache),
                gc_collections=0
            )

    async def cleanup_if_needed(self, force: bool = False) -> bool:
        """Clean up memory if usage is too high."""
        stats = await self.check_memory_usage()

        if stats.current_mb > self._cleanup_threshold or force:
            if not force:
                logger.warning(f"Memory usage ({stats.current_mb:.1f}MB) exceeds threshold ({self._cleanup_threshold:.1f}MB)")

            # Progressive cleanup strategy
            cleaned = await self._progressive_cleanup(stats.current_mb)

            if cleaned:
                new_stats = await self.check_memory_usage()
                logger.info(f"Memory cleanup completed: {stats.current_mb:.1f}MB -> {new_stats.current_mb:.1f}MB")

            return cleaned

        return False

    async def _progressive_cleanup(self, current_mb: float) -> bool:
        """Progressive memory cleanup strategy."""
        cleaned = False

        # Level 1: Clear caches
        if current_mb > self._cleanup_threshold:
            cache_size_before = len(self.cache)
            self.cache.clear()
            cleaned = True
            logger.debug(f"Level 1 cleanup: Cleared {cache_size_before} cache entries")

        # Level 2: Force garbage collection
        if current_mb > self.max_memory_mb * 0.9:
            collected = gc.collect()
            cleaned = True
            logger.debug(f"Level 2 cleanup: Collected {collected} objects")

        # Level 3: Clear weak references and force full GC
        if current_mb > self.max_memory_mb:
            self.weak_refs.clear()

            # Multiple GC passes for thorough cleanup
            for i in range(3):
                collected = gc.collect()
                if collected == 0:
                    break

            cleaned = True
            logger.debug(f"Level 3 cleanup: Emergency cleanup completed")

        return cleaned

    async def monitor_memory_continuously(self, callback=None):
        """Continuous memory monitoring (for background tasks)."""
        stats = await self.check_memory_usage()

        if callback:
            await callback(stats)

        # Auto cleanup if needed
        if stats.current_mb > self._cleanup_threshold:
            await self.cleanup_if_needed()

    def cache_get(self, key: str) -> Optional[Any]:
        """Get from memory cache."""
        return self.cache.get(key)

    def cache_set(self, key: str, value: Any, max_size: int = 10000):
        """Set in memory cache with automatic cleanup."""
        if len(self.cache) >= max_size:
            # Remove oldest 20% of cache entries (simple LRU approximation)
            keys_to_remove = list(self.cache.keys())[:max_size // 5]
            for k in keys_to_remove:
                self.cache.pop(k, None)

            logger.debug(f"Cache cleanup: removed {len(keys_to_remove)} entries")

        self.cache[key] = value

    def cache_clear(self):
        """Clear all cache entries."""
        cache_size = len(self.cache)
        self.cache.clear()
        logger.debug(f"Cleared {cache_size} cache entries")

    def add_weak_reference(self, key: str, obj: Any):
        """Add weak reference to track objects."""
        try:
            self.weak_refs[key] = obj
        except TypeError:
            # Object doesn't support weak references
            pass

    def get_weak_reference(self, key: str) -> Optional[Any]:
        """Get object from weak references."""
        return self.weak_refs.get(key)

    async def get_detailed_memory_info(self) -> Dict[str, Any]:
        """Get detailed memory information for monitoring."""
        stats = await self.check_memory_usage()

        try:
            import psutil
            import os

            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()

            return {
                'rss_mb': memory_info.rss / 1024 / 1024,
                'vms_mb': memory_info.vms / 1024 / 1024,
                'memory_percent': memory_percent,
                'cache_entries': len(self.cache),
                'weak_refs': len(self.weak_refs),
                'gc_collections': stats.gc_collections,
                'threshold_mb': self._cleanup_threshold,
                'limit_mb': self.max_memory_mb,
                'utilization_percent': (stats.current_mb / self.max_memory_mb) * 100
            }
        except ImportError:
            return {
                'cache_entries': len(self.cache),
                'weak_refs': len(self.weak_refs),
                'threshold_mb': self._cleanup_threshold,
                'limit_mb': self.max_memory_mb
            }

    def set_memory_limit(self, limit_mb: int):
        """Update memory limit and cleanup threshold."""
        self.max_memory_mb = limit_mb
        self._cleanup_threshold = limit_mb * 0.8
        logger.info(f"Updated memory limit to {limit_mb}MB (threshold: {self._cleanup_threshold:.1f}MB)")

    async def optimize_for_batch_size(self, batch_size: int):
        """Optimize memory settings based on expected batch size."""
        # Estimate memory needs based on batch size
        estimated_mb_per_job = 0.5  # Rough estimate
        estimated_total_mb = batch_size * estimated_mb_per_job

        # Adjust cache limits based on batch size
        if estimated_total_mb > self.max_memory_mb * 0.5:
            # Large batch - reduce cache size
            max_cache_size = max(1000, int(self.max_memory_mb * 100))  # Scale with memory limit
        else:
            # Normal batch - standard cache size
            max_cache_size = 10000

        logger.debug(f"Optimized for batch size {batch_size}: cache limit = {max_cache_size}")
        return max_cache_size