"""Deduplication services package."""

from .bloom_filter import DuplicationBloomFilter
from .similarity_calculator import SimilarityCalculator
from .cross_source_detector import CrossSourceDetector, CrossSourceDuplicateMatch
from .group_manager import DuplicateGroupsManager
from .memory_manager import DeduplicationMemoryManager, MemoryStats
from .health_checker import DeduplicationHealthChecker

__all__ = [
    "DuplicationBloomFilter",
    "SimilarityCalculator",
    "CrossSourceDetector",
    "CrossSourceDuplicateMatch",
    "DuplicateGroupsManager",
    "DeduplicationMemoryManager",
    "MemoryStats",
    "DeduplicationHealthChecker"

]