"""Comprehensive configuration system for job deduplication."""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from pydantic import Field, validator
from pydantic_settings import BaseSettings
from enum import Enum

logger = logging.getLogger(__name__)


class DeduplicationMode(str, Enum):
    """Deduplication operation modes."""
    STRICT = "strict"       # High precision, low recall
    BALANCED = "balanced"   # Balanced precision and recall
    AGGRESSIVE = "aggressive"  # High recall, may have more false positives


class SimilarityAlgorithm(str, Enum):
    """Available similarity algorithms."""
    FUZZY_RATIO = "fuzzy_ratio"
    TOKEN_SORT = "token_sort"
    TOKEN_SET = "token_set"
    COMBINED = "combined"


class DeduplicationConfig(BaseSettings):
    """
    Comprehensive deduplication configuration with validation.

    Supports multiple environments and runtime configuration updates.
    """

    # Core operation mode
    mode: DeduplicationMode = Field(
        default=DeduplicationMode.BALANCED,
        description="Deduplication operation mode affecting precision/recall balance"
    )

    # Similarity thresholds by mode
    similarity_thresholds: Dict[str, float] = Field(
        default={
            "exact": 1.0,
            "high": 0.95,
            "medium": 0.85,
            "low": 0.75,
            "review": 0.70
        },
        description="Similarity score thresholds for different confidence levels"
    )

    # Mode-specific threshold adjustments
    mode_threshold_adjustments: Dict[DeduplicationMode, Dict[str, float]] = Field(
        default={
            DeduplicationMode.STRICT: {
                "high": 0.98,
                "medium": 0.92,
                "low": 0.85
            },
            DeduplicationMode.AGGRESSIVE: {
                "high": 0.90,
                "medium": 0.80,
                "low": 0.70
            },
            DeduplicationMode.BALANCED: {}  # Use defaults
        },
        description="Threshold adjustments per mode"
    )

    # Similarity calculation weights
    similarity_weights: Dict[str, float] = Field(
        default={
            "title": 0.35,
            "company": 0.25,
            "location": 0.20,
            "salary": 0.10,
            "date": 0.05,
            "description": 0.05
        },
        description="Weights for different factors in similarity calculation"
    )

    @validator('similarity_weights')
    def validate_weights_sum_to_one(cls, v):
        total = sum(v.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Similarity weights must sum to 1.0, got {total}")
        return v

    # Algorithm configuration
    primary_algorithm: SimilarityAlgorithm = Field(
        default=SimilarityAlgorithm.COMBINED,
        description="Primary similarity algorithm to use"
    )

    algorithm_weights: Dict[SimilarityAlgorithm, float] = Field(
        default={
            SimilarityAlgorithm.FUZZY_RATIO: 0.25,
            SimilarityAlgorithm.TOKEN_SORT: 0.35,
            SimilarityAlgorithm.TOKEN_SET: 0.40
        },
        description="Weights for combining multiple algorithms"
    )

    # Performance configuration
    batch_processing: Dict[str, Any] = Field(
        default={
            "batch_size": 100,
            "max_concurrent_tasks": 10,
            "chunk_size": 500,
            "memory_limit_mb": 500,
            "processing_timeout_seconds": 30
        },
        description="Batch processing performance settings"
    )

    # Bloom filter configuration
    bloom_filter: Dict[str, Any] = Field(
        default={
            "enabled": True,
            "capacity": 1000000,
            "error_rate": 0.001,
            "reset_interval_days": 30,
            "warm_on_startup": True
        },
        description="Bloom filter settings for performance optimization"
    )

    # Caching configuration
    caching: Dict[str, Any] = Field(
        default={
            "enabled": True,
            "redis_ttl_seconds": 3600,
            "company_cache_size": 5000,
            "hash_cache_size": 10000,
            "preload_recent_days": 7
        },
        description="Redis caching configuration"
    )

    # Cross-source detection
    cross_source: Dict[str, Any] = Field(
        default={
            "enabled": True,
            "threshold_boost": 0.05,
            "temporal_window_days": 21,
            "source_priorities": {
                1: 1,    # Direct company postings
                2: 2,    # Premium job boards
                4: 4,    # RemoteOK
                999: 999 # Default/unknown
            }
        },
        description="Cross-source duplicate detection settings"
    )

    # Group management
    group_management: Dict[str, Any] = Field(
        default={
            "max_group_size": 50,
            "auto_merge_threshold": 0.90,
            "split_threshold": 0.70,
            "quality_threshold": 0.80,
            "primary_selection_weights": {
                "completeness": 0.30,
                "quality": 0.30,
                "freshness": 0.20,
                "source_priority": 0.20
            }
        },
        description="Duplicate group management settings"
    )

    # Quality and validation
    quality_control: Dict[str, Any] = Field(
        default={
            "min_quality_score": 0.30,
            "spam_detection_threshold": 70,
            "validation_sampling_rate": 0.10,
            "false_positive_tolerance": 0.05,
            "accuracy_target": 0.95
        },
        description="Quality control and validation settings"
    )

    # Monitoring and alerting
    monitoring: Dict[str, Any] = Field(
        default={
            "metrics_enabled": True,
            "alert_thresholds": {
                "min_jobs_per_second": 50,
                "min_accuracy_rate": 0.90,
                "max_memory_mb": 400,
                "max_processing_time_seconds": 20,
                "max_false_positive_rate": 0.10
            },
            "retention_days": 30,
            "performance_sampling_rate": 1.0
        },
        description="Monitoring and alerting configuration"
    )

    # Environment-specific overrides
    environment: str = Field(
        default=os.getenv("ENVIRONMENT", "development"),
        description="Current environment (development, staging, production)"
    )

    # Feature flags
    feature_flags: Dict[str, bool] = Field(
        default={
            "advanced_similarity": True,
            "parallel_processing": True,
            "auto_group_merging": True,
            "real_time_monitoring": True,
            "experimental_algorithms": False
        },
        description="Feature flags for enabling/disabling features"
    )

    class Config:
        env_prefix = "DEDUP_"
        case_sensitive = False

    def get_effective_thresholds(self) -> Dict[str, float]:
        """Get similarity thresholds adjusted for current mode."""
        base_thresholds = self.similarity_thresholds.copy()
        mode_adjustments = self.mode_threshold_adjustments.get(self.mode, {})

        # Apply mode-specific adjustments
        for threshold_name, adjustment in mode_adjustments.items():
            if threshold_name in base_thresholds:
                base_thresholds[threshold_name] = adjustment

        return base_thresholds

    def get_algorithm_config(self) -> Dict[str, Any]:
        """Get algorithm configuration for current settings."""
        return {
            "primary": self.primary_algorithm,
            "weights": self.algorithm_weights,
            "combined_enabled": self.primary_algorithm == SimilarityAlgorithm.COMBINED
        }

    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check if a feature is enabled."""
        return self.feature_flags.get(feature_name, False)

    def validate_configuration(self) -> List[str]:
        """Validate configuration and return any issues."""
        issues = []

        # Validate threshold ranges
        thresholds = self.get_effective_thresholds()
        for name, value in thresholds.items():
            if not 0.0 <= value <= 1.0:
                issues.append(f"Threshold '{name}' value {value} is outside valid range [0.0, 1.0]")

        # Validate weights
        if abs(sum(self.similarity_weights.values()) - 1.0) > 0.01:
            issues.append("Similarity weights do not sum to 1.0")

        # Validate performance settings
        batch_config = self.batch_processing
        if batch_config["batch_size"] <= 0:
            issues.append("Batch size must be positive")

        if batch_config["max_concurrent_tasks"] <= 0:
            issues.append("Max concurrent tasks must be positive")

        # Validate bloom filter settings
        bloom_config = self.bloom_filter
        if bloom_config["capacity"] <= 0:
            issues.append("Bloom filter capacity must be positive")

        if not 0.0 < bloom_config["error_rate"] < 1.0:
            issues.append("Bloom filter error rate must be between 0 and 1")

        return issues


# Global configuration instance
dedup_config = DeduplicationConfig()


def get_dedup_config() -> DeduplicationConfig:
    """Get the global deduplication configuration."""
    return dedup_config


def reload_config() -> DeduplicationConfig:
    """Reload configuration from environment."""
    global dedup_config
    dedup_config = DeduplicationConfig()
    return dedup_config


# Legacy configuration dictionary for backwards compatibility
DEDUP_CONFIG: Dict[str, Any] = {
    # Similarity thresholds
    "thresholds": {
        "exact_match": 1.0,           # 100% match
        "high_similarity": 0.95,      # 95% match - likely duplicate
        "medium_similarity": 0.85,    # 85% match - possible duplicate
        "low_similarity": 0.70,       # 70% match - review needed
    },

    # Hash-based matching
    "hash_matching": {
        "enable_title_hash": True,
        "enable_content_hash": True,
        "enable_company_hash": True,
        "hash_similarity_threshold": 0.9,
    },

    # Enhanced similarity weights and thresholds
    "similarity_weights": {
        "title": 0.35,               # Weight for title similarity
        "company": 0.25,             # Weight for company similarity
        "location": 0.20,            # Weight for location similarity
        "salary": 0.10,              # Weight for salary similarity
        "date": 0.05,                # Weight for date proximity
        "description": 0.05          # Weight for description similarity
    },

    "similarity_thresholds": {
        "exact": 1.0,                # 100% match
        "high": 0.95,                # 95%+ likely duplicate
        "medium": 0.85,              # 85%+ possible duplicate
        "low": 0.75,                 # 75%+ worth investigating
        "review": 0.70               # 70%+ needs manual review
    },

    "algorithm_weights": {
        "title_algorithms": {
            "ratio": 0.25,           # Basic string similarity
            "partial_ratio": 0.30,   # Substring matching
            "token_sort": 0.25,      # Word order independence
            "token_set": 0.20        # Set-based comparison
        }
    },

    # Fuzzy matching configuration (legacy - kept for compatibility)
    "fuzzy_matching": {
        "title_weight": 0.4,          # Weight for title similarity
        "company_weight": 0.3,        # Weight for company similarity
        "location_weight": 0.2,       # Weight for location similarity
        "description_weight": 0.1,    # Weight for description similarity
        "min_title_length": 10,       # Minimum title length for fuzzy matching
        "levenshtein_threshold": 0.8, # Threshold for Levenshtein distance
    },

    # Bloom filter configuration
    "bloom_filter": {
        "capacity": 1_000_000,        # 1M items
        "error_rate": 0.001,          # 0.1% false positive rate
        "reset_interval_days": 30,    # Monthly reset
        "warm_on_startup": True,      # Warm filter on service startup
    },

    # Performance optimization
    "performance": {
        "enable_bloom_filter": True,
        "bloom_filter_threshold": 0.001,  # Disable if error rate exceeds this
        "batch_size": 100,                # Batch size for processing
        "max_concurrent_jobs": 50,        # Max concurrent job processing
        "database_query_timeout": 30,     # Database query timeout in seconds
        "redis_timeout": 5,               # Redis timeout in seconds
    },

    # Advanced performance settings
    "batch_size": 100,                    # Jobs per batch
    "max_concurrent_tasks": 10,           # Parallel processing limit
    "cache_preload_size": 1000,          # Pre-load cache size
    "memory_limit_mb": 500,               # Memory limit for processing
    "chunk_size": 500,                    # Chunk size for large batches

    # Database optimization
    "connection_pool_size": 20,           # Database connections
    "query_timeout_seconds": 30,          # Query timeout
    "batch_insert_size": 500,            # Batch insert size

    # Cache optimization
    "redis_cache_ttl": 3600,             # 1 hour TTL
    "company_cache_size": 5000,          # Company cache entries
    "hash_cache_size": 10000,            # Content hash cache entries

    # Performance targets
    "target_jobs_per_second": 67,        # 1000 jobs in 15 seconds
    "max_processing_time_seconds": 15,   # Maximum batch processing time

    # Cross-source detection
    "cross_source": {
        "enable": True,
        "source_priority": {
            "remoteok": 2,    # Medium priority
        },
        "max_age_days": 30,   # Maximum age for cross-source matching
    },

    # Source priority mapping (lower number = higher priority)
    "source_priorities": {
        1: 1,    # Direct company postings (highest priority)
        2: 2,    # Premium job boards
        4: 4,    # RemoteOK
        5: 5,    # Indeed scraping
        6: 6,    # Generic scrapers
        999: 999 # Unknown/default (lowest priority)
    },

    # Cross-source specific thresholds
    "cross_source_threshold": 0.90,        # Higher than same-source (0.85)
    "cross_source_temporal_window": 21,    # Days to search for cross-source matches

    # Merge preferences
    "merge_preferences": {
        "prefer_disclosed_salary": True,
        "prefer_longer_description": True,
        "prefer_direct_apply_urls": True,
        "merge_skills_and_benefits": True,
        "quality_score_weight": 0.3,
        "recency_weight": 0.2
    },

    # Duplicate group management
    "group_management": {
        "max_group_size": 50,         # Maximum jobs per duplicate group
        "auto_select_primary": True,  # Auto-select primary job in group
        "quality_score_threshold": 0.8,  # Minimum quality score for primary
        "prefer_recent_jobs": True,   # Prefer more recent jobs as primary
        "merge_similar_groups": True, # Merge groups with high similarity
    },

    # Group management specific settings
    "max_group_size": 50,
    "group_quality_threshold": 0.8,
    "auto_merge_threshold": 0.9,

    # Primary selection weights
    "primary_selection_weights": {
        "completeness": 0.3,
        "quality": 0.3,
        "freshness": 0.2,
        "source_priority": 0.2
    },

    # Group optimization
    "group_split_threshold": 0.7,          # Split if similarity drops below this
    "group_merge_candidate_threshold": 0.85,  # Consider merging above this
    "group_maintenance_interval_hours": 24,    # How often to run group maintenance

    # Review queue configuration
    "review_queue": {
        "enable": True,
        "similarity_range": {
            "min": 0.70,              # Minimum similarity for review
            "max": 0.85,              # Maximum similarity for review
        },
        "max_queue_size": 1000,       # Maximum items in review queue
        "auto_resolve_threshold": 0.95,  # Auto-resolve above this threshold
        "priority_weights": {
            "similarity_score": 0.4,
            "job_recency": 0.3,
            "source_priority": 0.3,
        },
    },

    # Monitoring and metrics
    "monitoring": {
        "enable_metrics": True,
        "metrics_retention_days": 90,
        "performance_tracking": True,
        "accuracy_tracking": True,
        "alert_thresholds": {
            "processing_time_ms": 67,     # Alert if processing > 67ms per job
            "false_positive_rate": 0.05,  # Alert if FPR > 5%
            "memory_usage_mb": 500,       # Alert if memory > 500MB
        },
    },

    # Caching configuration
    "caching": {
        "enable_redis_cache": True,
        "cache_ttl_seconds": 3600,        # 1 hour TTL
        "max_cache_size_mb": 100,         # Maximum cache size
        "cache_key_prefix": "dedup:",     # Prefix for cache keys
        "warm_cache_on_startup": True,    # Warm cache on startup
    },

    # Database optimization
    "database": {
        "use_read_replica": False,        # Use read replica for queries
        "connection_pool_size": 10,       # Connection pool size
        "query_timeout_seconds": 30,      # Query timeout
        "batch_insert_size": 1000,        # Batch size for inserts
        "enable_query_logging": False,    # Log slow queries
    },

    # Advanced features
    "advanced": {
        "enable_ml_similarity": False,    # Enable ML-based similarity (future)
        "enable_semantic_search": False,  # Enable semantic similarity (future)
        "enable_location_fuzzing": True,  # Enable location normalization
        "enable_salary_matching": True,   # Consider salary in matching
        "company_name_normalization": True,  # Normalize company names
        "cross_source_boost": 0.05,      # Boost for cross-source matches
        "date_window_days": 14,          # Date window for temporal proximity
        "confidence_threshold": 0.7,     # Minimum confidence for matches
        "enable_synonym_matching": True, # Enable job title synonym matching
        "enable_company_aliases": True,  # Enable known company alias matching
    },

    # Development and testing
    "development": {
        "enable_debug_logging": False,
        "save_comparison_data": False,    # Save comparison data for analysis
        "mock_external_apis": False,      # Mock external APIs for testing
        "performance_profiling": False,   # Enable performance profiling
    },
}

# Environment-specific overrides
PRODUCTION_OVERRIDES = {
    "bloom_filter": {
        "capacity": 5_000_000,        # 5M capacity in production
    },
    "performance": {
        "max_concurrent_jobs": 100,   # Higher concurrency in production
    },
    "monitoring": {
        "enable_metrics": True,
        "performance_tracking": True,
        "accuracy_tracking": True,
    },
    "development": {
        "enable_debug_logging": False,
        "save_comparison_data": False,
        "performance_profiling": False,
    },
}

STAGING_OVERRIDES = {
    "bloom_filter": {
        "capacity": 1_000_000,
    },
    "development": {
        "enable_debug_logging": True,
        "save_comparison_data": True,
    },
}

DEVELOPMENT_OVERRIDES = {
    "bloom_filter": {
        "capacity": 100_000,          # Smaller capacity for development
    },
    "performance": {
        "max_concurrent_jobs": 10,    # Lower concurrency for development
    },
    "development": {
        "enable_debug_logging": True,
        "save_comparison_data": True,
        "performance_profiling": True,
    },
}


def get_dedup_config_legacy(environment: str = "development") -> Dict[str, Any]:
    """Get deduplication configuration for specified environment (legacy)."""
    config = DEDUP_CONFIG.copy()

    if environment == "production":
        # Apply production overrides
        for key, value in PRODUCTION_OVERRIDES.items():
            if key in config:
                config[key].update(value)
            else:
                config[key] = value
    elif environment == "staging":
        # Apply staging overrides
        for key, value in STAGING_OVERRIDES.items():
            if key in config:
                config[key].update(value)
            else:
                config[key] = value
    elif environment == "development":
        # Apply development overrides
        for key, value in DEVELOPMENT_OVERRIDES.items():
            if key in config:
                config[key].update(value)
            else:
                config[key] = value

    return config


def get_dedup_config(environment: str = "development") -> DeduplicationConfig:
    """Get deduplication configuration for specified environment."""
    # Set environment and create config instance
    os.environ["ENVIRONMENT"] = environment
    return DeduplicationConfig()