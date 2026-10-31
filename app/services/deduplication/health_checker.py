"""Comprehensive health checking for deduplication system."""

import logging
import asyncio
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from ...core.redis import get_redis_client
from ...core.database import db
from ...config.deduplication_config import get_dedup_config
from .bloom_filter import DuplicationBloomFilter
from .memory_manager import DeduplicationMemoryManager

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check operation."""
    component: str
    status: str  # healthy, warning, critical, unknown
    message: str
    response_time_ms: float
    details: Dict[str, Any]
    timestamp: datetime


class DeduplicationHealthChecker:
    """
    Comprehensive health checker for the deduplication system.

    Features:
    - Component-level health monitoring
    - Performance benchmarking
    - Dependency validation
    - Alert threshold monitoring
    - System readiness checks
    """

    def __init__(self, environment: str = "development"):
        self.environment = environment
        self.config = get_dedup_config(environment)
        self.redis = get_redis_client()
        self.memory_manager = DeduplicationMemoryManager()

        # Health check intervals
        self.check_intervals = {
            'database': 30,      # seconds
            'redis': 15,         # seconds
            'bloom_filter': 60,  # seconds
            'memory': 10,        # seconds
            'performance': 120   # seconds
        }

        self.last_checks = {}
        self.cached_results = {}

    async def run_comprehensive_health_check(self) -> Dict[str, Any]:
        """Run all health checks and return comprehensive status."""
        try:
            start_time = time.time()

            # Run all health checks concurrently
            tasks = [
                self._check_database_health(),
                self._check_redis_health(),
                self._check_bloom_filter_health(),
                self._check_memory_health(),
                self._check_performance_health(),
                self._check_configuration_health()
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            health_results = []
            overall_status = "healthy"

            for result in results:
                if isinstance(result, Exception):
                    health_results.append(HealthCheckResult(
                        component="unknown",
                        status="critical",
                        message=f"Health check failed: {str(result)}",
                        response_time_ms=0,
                        details={},
                        timestamp=datetime.utcnow()
                    ))
                    overall_status = "critical"
                else:
                    health_results.append(result)
                    if result.status == "critical":
                        overall_status = "critical"
                    elif result.status == "warning" and overall_status == "healthy":
                        overall_status = "warning"

            total_time = (time.time() - start_time) * 1000

            return {
                'overall_status': overall_status,
                'total_check_time_ms': total_time,
                'timestamp': datetime.utcnow().isoformat(),
                'environment': self.environment,
                'components': [
                    {
                        'component': result.component,
                        'status': result.status,
                        'message': result.message,
                        'response_time_ms': result.response_time_ms,
                        'details': result.details
                    }
                    for result in health_results
                ],
                'summary': {
                    'healthy': sum(1 for r in health_results if r.status == "healthy"),
                    'warning': sum(1 for r in health_results if r.status == "warning"),
                    'critical': sum(1 for r in health_results if r.status == "critical"),
                    'total': len(health_results)
                }
            }

        except Exception as e:
            logger.error(f"Error in comprehensive health check: {e}")
            return {
                'overall_status': 'critical',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    async def _check_database_health(self) -> HealthCheckResult:
        """Check database connectivity and performance."""
        start_time = time.time()

        try:
            async with db.get_session() as session:
                # Test basic connectivity
                result = await session.execute("SELECT 1")
                result.fetchone()

                # Test deduplication tables
                await session.execute("SELECT COUNT(*) FROM jobs LIMIT 1")
                await session.execute("SELECT COUNT(*) FROM duplicate_groups LIMIT 1")
                await session.execute("SELECT COUNT(*) FROM duplicate_mappings LIMIT 1")

                response_time = (time.time() - start_time) * 1000

                # Check performance
                status = "healthy"
                message = "Database is healthy"
                details = {'response_time_ms': response_time}

                if response_time > 1000:  # > 1 second
                    status = "warning"
                    message = f"Database response time is high: {response_time:.1f}ms"
                elif response_time > 5000:  # > 5 seconds
                    status = "critical"
                    message = f"Database response time is critical: {response_time:.1f}ms"

                return HealthCheckResult(
                    component="database",
                    status=status,
                    message=message,
                    response_time_ms=response_time,
                    details=details,
                    timestamp=datetime.utcnow()
                )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                component="database",
                status="critical",
                message=f"Database check failed: {str(e)}",
                response_time_ms=response_time,
                details={'error': str(e)},
                timestamp=datetime.utcnow()
            )

    async def _check_redis_health(self) -> HealthCheckResult:
        """Check Redis connectivity and performance."""
        start_time = time.time()

        try:
            # Test basic operations
            test_key = "dedup_health_check"
            await self.redis.set(test_key, "test_value", ex=10)
            value = await self.redis.get(test_key)
            await self.redis.delete(test_key)

            if value != "test_value":
                raise Exception("Redis read/write test failed")

            response_time = (time.time() - start_time) * 1000

            # Check Redis memory usage
            info = await self.redis.info('memory')
            memory_usage_mb = info.get('used_memory', 0) / (1024 * 1024)

            status = "healthy"
            message = "Redis is healthy"
            details = {
                'response_time_ms': response_time,
                'memory_usage_mb': memory_usage_mb
            }

            if response_time > 500:  # > 500ms
                status = "warning"
                message = f"Redis response time is high: {response_time:.1f}ms"
            elif memory_usage_mb > 1000:  # > 1GB
                status = "warning"
                message = f"Redis memory usage is high: {memory_usage_mb:.1f}MB"

            return HealthCheckResult(
                component="redis",
                status=status,
                message=message,
                response_time_ms=response_time,
                details=details,
                timestamp=datetime.utcnow()
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                component="redis",
                status="critical",
                message=f"Redis check failed: {str(e)}",
                response_time_ms=response_time,
                details={'error': str(e)},
                timestamp=datetime.utcnow()
            )

    async def _check_bloom_filter_health(self) -> HealthCheckResult:
        """Check bloom filter status and performance."""
        start_time = time.time()

        try:
            bloom_filter = DuplicationBloomFilter()

            # Test bloom filter operations
            test_hash = "test_hash_12345"
            await bloom_filter.add(test_hash)
            exists = await bloom_filter.might_exist(test_hash)

            if not exists:
                raise Exception("Bloom filter test failed")

            # Get bloom filter stats
            stats = await bloom_filter.get_stats()

            response_time = (time.time() - start_time) * 1000

            status = "healthy"
            message = "Bloom filter is healthy"
            details = {
                'response_time_ms': response_time,
                'stats': stats
            }

            # Check error rate
            error_rate = stats.get('estimated_error_rate', 0)
            threshold = self.config.bloom_filter['error_rate']

            if error_rate > threshold * 2:
                status = "warning"
                message = f"Bloom filter error rate is high: {error_rate:.4f}"
            elif error_rate > threshold * 5:
                status = "critical"
                message = f"Bloom filter error rate is critical: {error_rate:.4f}"

            return HealthCheckResult(
                component="bloom_filter",
                status=status,
                message=message,
                response_time_ms=response_time,
                details=details,
                timestamp=datetime.utcnow()
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                component="bloom_filter",
                status="critical",
                message=f"Bloom filter check failed: {str(e)}",
                response_time_ms=response_time,
                details={'error': str(e)},
                timestamp=datetime.utcnow()
            )

    async def _check_memory_health(self) -> HealthCheckResult:
        """Check memory usage and health."""
        start_time = time.time()

        try:
            memory_stats = await self.memory_manager.get_memory_stats()
            response_time = (time.time() - start_time) * 1000

            current_mb = memory_stats.current_memory_mb
            limit_mb = self.config.get('memory_limit_mb', 500)
            usage_percentage = (current_mb / limit_mb) * 100

            status = "healthy"
            message = f"Memory usage: {current_mb:.1f}MB ({usage_percentage:.1f}%)"

            if usage_percentage > 80:
                status = "warning"
                message = f"Memory usage is high: {current_mb:.1f}MB ({usage_percentage:.1f}%)"
            elif usage_percentage > 95:
                status = "critical"
                message = f"Memory usage is critical: {current_mb:.1f}MB ({usage_percentage:.1f}%)"

            details = {
                'response_time_ms': response_time,
                'memory_stats': {
                    'current_mb': current_mb,
                    'peak_mb': memory_stats.peak_memory_mb,
                    'limit_mb': limit_mb,
                    'usage_percentage': usage_percentage,
                    'available_mb': memory_stats.available_memory_mb
                }
            }

            return HealthCheckResult(
                component="memory",
                status=status,
                message=message,
                response_time_ms=response_time,
                details=details,
                timestamp=datetime.utcnow()
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                component="memory",
                status="critical",
                message=f"Memory check failed: {str(e)}",
                response_time_ms=response_time,
                details={'error': str(e)},
                timestamp=datetime.utcnow()
            )

    async def _check_performance_health(self) -> HealthCheckResult:
        """Check system performance metrics."""
        start_time = time.time()

        try:
            # Get recent performance data from Redis
            pattern = "dedup_metrics:batch:*"
            keys = await self.redis.keys(pattern)

            if not keys:
                return HealthCheckResult(
                    component="performance",
                    status="warning",
                    message="No recent performance data available",
                    response_time_ms=(time.time() - start_time) * 1000,
                    details={},
                    timestamp=datetime.utcnow()
                )

            # Get latest batch metrics
            latest_key = max(keys, key=lambda k: int(k.decode().split(':')[-1]))
            metrics_json = await self.redis.get(latest_key)

            if not metrics_json:
                raise Exception("Could not retrieve performance metrics")

            import json
            metrics = json.loads(metrics_json)

            response_time = (time.time() - start_time) * 1000

            # Evaluate performance
            jobs_per_second = metrics.get('jobs_per_second', 0)
            target_jps = self.config.get('target_jobs_per_second', 67)
            accuracy_rate = metrics.get('accuracy_rate', 0)

            status = "healthy"
            message = f"Performance: {jobs_per_second:.1f} jobs/sec, {accuracy_rate:.1%} accuracy"

            if jobs_per_second < target_jps * 0.8:  # Below 80% of target
                status = "warning"
                message = f"Performance below target: {jobs_per_second:.1f}/{target_jps} jobs/sec"
            elif jobs_per_second < target_jps * 0.5:  # Below 50% of target
                status = "critical"
                message = f"Performance critically low: {jobs_per_second:.1f}/{target_jps} jobs/sec"

            if accuracy_rate < 0.9:  # Below 90% accuracy
                status = "warning" if status == "healthy" else "critical"
                message += f", low accuracy: {accuracy_rate:.1%}"

            details = {
                'response_time_ms': response_time,
                'performance_metrics': {
                    'jobs_per_second': jobs_per_second,
                    'target_jobs_per_second': target_jps,
                    'accuracy_rate': accuracy_rate,
                    'processing_time_seconds': metrics.get('processing_time_seconds', 0),
                    'jobs_processed': metrics.get('total_jobs_processed', 0)
                }
            }

            return HealthCheckResult(
                component="performance",
                status=status,
                message=message,
                response_time_ms=response_time,
                details=details,
                timestamp=datetime.utcnow()
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                component="performance",
                status="critical",
                message=f"Performance check failed: {str(e)}",
                response_time_ms=response_time,
                details={'error': str(e)},
                timestamp=datetime.utcnow()
            )

    async def _check_configuration_health(self) -> HealthCheckResult:
        """Check configuration validity."""
        start_time = time.time()

        try:
            # Validate key configuration values
            config_issues = []

            # Check performance targets
            target_jps = self.config.get('target_jobs_per_second', 0)
            if target_jps <= 0:
                config_issues.append("Invalid target_jobs_per_second")

            # Check bloom filter config
            bf_config = self.config.get('bloom_filter', {})
            if bf_config.get('capacity', 0) <= 0:
                config_issues.append("Invalid bloom filter capacity")

            # Check memory limits
            memory_limit = self.config.get('memory_limit_mb', 0)
            if memory_limit <= 0:
                config_issues.append("Invalid memory limit")

            response_time = (time.time() - start_time) * 1000

            if config_issues:
                return HealthCheckResult(
                    component="configuration",
                    status="critical",
                    message=f"Configuration issues: {', '.join(config_issues)}",
                    response_time_ms=response_time,
                    details={'issues': config_issues},
                    timestamp=datetime.utcnow()
                )

            return HealthCheckResult(
                component="configuration",
                status="healthy",
                message="Configuration is valid",
                response_time_ms=response_time,
                details={
                    'environment': self.environment,
                    'target_performance': target_jps,
                    'memory_limit_mb': memory_limit
                },
                timestamp=datetime.utcnow()
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                component="configuration",
                status="critical",
                message=f"Configuration check failed: {str(e)}",
                response_time_ms=response_time,
                details={'error': str(e)},
                timestamp=datetime.utcnow()
            )

    async def get_system_readiness(self) -> Dict[str, Any]:
        """Check if the system is ready to process jobs."""
        try:
            health_check = await self.run_comprehensive_health_check()

            # System is ready if no critical issues
            ready = health_check['overall_status'] != 'critical'

            return {
                'ready': ready,
                'status': health_check['overall_status'],
                'message': f"System is {'ready' if ready else 'not ready'} for processing",
                'components_summary': health_check['summary'],
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error checking system readiness: {e}")
            return {
                'ready': False,
                'status': 'critical',
                'message': f"Readiness check failed: {str(e)}",
                'timestamp': datetime.utcnow().isoformat()
            }