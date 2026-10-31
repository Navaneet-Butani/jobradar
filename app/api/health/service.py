"""Health service for managing health checks and monitoring."""

import time
import logging
from typing import Dict, Any, List
from datetime import datetime

from ...core.database import db
from ...core.redis import redis_manager
from ...config.settings import settings
from .schema import HealthCheckResponse, DetailedHealthCheckResponse, ServiceHealthStatus
from ...services.deduplication.bloom_filter import DuplicationBloomFilter
from ...services.deduplication.health_checker import DeduplicationHealthChecker

logger = logging.getLogger(__name__)


class HealthService:
    """Service for managing application health checks."""
    
    @staticmethod
    async def basic_health_check() -> HealthCheckResponse:
        """Perform basic health check for core services."""
        try:
            # Check PostgreSQL connection
            postgres_healthy = await HealthService._check_postgres_health()
            logger.info(f"PostgreSQL health check: {postgres_healthy}")
            
            # Check Redis connection
            redis_healthy = await HealthService._check_redis_health()
            logger.info(f"Redis health check: {redis_healthy}")
            
            # Determine overall health
            overall_healthy = postgres_healthy and redis_healthy
            
            return HealthCheckResponse(
                postgres=postgres_healthy,
                redis=redis_healthy,
                overall_status=overall_healthy
            )
            
        except Exception as e:
            logger.error(f"Basic health check failed: {e}")
            return HealthCheckResponse(
                postgres=False,
                redis=False,
                overall_status=False
            )
    
    @staticmethod
    async def detailed_health_check() -> DetailedHealthCheckResponse:
        """Perform detailed health check with additional system information."""
        try:
            # Check PostgreSQL with timing
            start_time = time.time()
            postgres_healthy = await HealthService._check_postgres_health()
            postgres_response_time = (time.time() - start_time) * 1000
            
            # Check Redis with timing
            start_time = time.time()
            redis_healthy = await HealthService._check_redis_health()
            redis_response_time = (time.time() - start_time) * 1000
            
            # Build detailed response
            database_info = {
                "status": "healthy" if postgres_healthy else "unhealthy",
                "type": "PostgreSQL",
                "connection_pool": "active" if postgres_healthy else "inactive",
                "response_time_ms": round(postgres_response_time, 2),
                "version": await HealthService._get_postgres_version(),
                "active_connections": await HealthService._get_postgres_connections()
            }
            
            cache_info = {
                "status": "healthy" if redis_healthy else "unhealthy", 
                "type": "Redis",
                "connection": "active" if redis_healthy else "inactive",
                "response_time_ms": round(redis_response_time, 2),
                "version": await HealthService._get_redis_version(),
                "memory_usage": await HealthService._get_redis_memory_usage()
            }
            
            overall_health = postgres_healthy and redis_healthy
            
            return DetailedHealthCheckResponse(
                database=database_info,
                cache=cache_info,
                overall_health=overall_health
            )
            
        except Exception as e:
            logger.error(f"Detailed health check failed: {e}")
            return DetailedHealthCheckResponse(
                database={"status": "error", "type": "PostgreSQL", "error": str(e)},
                cache={"status": "error", "type": "Redis", "error": str(e)},
                overall_health=False
            )
    
    @staticmethod
    async def get_service_health_statuses() -> List[ServiceHealthStatus]:
        """Get health status for all monitored services."""
        services = []
        
        try:
            # PostgreSQL health
            start_time = time.time()
            postgres_healthy = await HealthService._check_postgres_health()
            postgres_response_time = (time.time() - start_time) * 1000
            
            services.append(ServiceHealthStatus(
                name="PostgreSQL Database",
                status="healthy" if postgres_healthy else "unhealthy",
                response_time_ms=round(postgres_response_time, 2),
                details={
                    "type": "PostgreSQL",
                    "version": await HealthService._get_postgres_version(),
                    "active_connections": await HealthService._get_postgres_connections()
                }
            ))
            
            # Redis health
            start_time = time.time()
            redis_healthy = await HealthService._check_redis_health()
            redis_response_time = (time.time() - start_time) * 1000
            
            services.append(ServiceHealthStatus(
                name="Redis Cache",
                status="healthy" if redis_healthy else "unhealthy",
                response_time_ms=round(redis_response_time, 2),
                details={
                    "type": "Redis",
                    "version": await HealthService._get_redis_version(),
                    "memory_usage": await HealthService._get_redis_memory_usage()
                }
            ))
            
            # Bloom Filter health check
            try:
                start_time = time.time()
                bloom_health = await HealthService._check_bloom_filter_health()
                bloom_response_time = (time.time() - start_time) * 1000

                services.append(ServiceHealthStatus(
                    name="Bloom Filter",
                    status=bloom_health.get('status', 'error'),
                    response_time_ms=round(bloom_response_time, 2),
                    details={
                        "type": "Deduplication Cache",
                        "implementation": bloom_health.get('implementation', 'Unknown'),
                        "capacity_used": bloom_health.get('capacity_used', '0'),
                        "hit_rate": bloom_health.get('hit_rate', '0%'),
                        "last_reset": bloom_health.get('last_reset', 'never'),
                        "error": bloom_health.get('error')
                    }
                ))
            except Exception as e:
                logger.error(f"Bloom filter health check failed: {e}")
                services.append(ServiceHealthStatus(
                    name="Bloom Filter",
                    status="error",
                    response_time_ms=0,
                    details={
                        "type": "Deduplication Cache",
                        "error": str(e)
                    }
                ))

            # Deduplication System health check
            try:
                start_time = time.time()
                dedup_health_checker = DeduplicationHealthChecker()
                dedup_health = await dedup_health_checker.run_comprehensive_health_check()
                dedup_response_time = (time.time() - start_time) * 1000

                services.append(ServiceHealthStatus(
                    name="Deduplication System",
                    status=dedup_health.get('overall_status', 'error'),
                    response_time_ms=round(dedup_response_time, 2),
                    details={
                        "type": "Job Deduplication Engine",
                        "components_summary": dedup_health.get('summary', {}),
                        "total_components": dedup_health.get('summary', {}).get('total', 0),
                        "healthy_components": dedup_health.get('summary', {}).get('healthy', 0),
                        "warning_components": dedup_health.get('summary', {}).get('warning', 0),
                        "critical_components": dedup_health.get('summary', {}).get('critical', 0),
                        "environment": dedup_health.get('environment', 'unknown')
                    }
                ))
            except Exception as e:
                logger.error(f"Deduplication system health check failed: {e}")
                services.append(ServiceHealthStatus(
                    name="Deduplication System",
                    status="error",
                    response_time_ms=0,
                    details={
                        "type": "Job Deduplication Engine",
                        "error": str(e)
                    }
                ))

            # Additional service checks can be added here
            # - Message queues
            # - File storage services

        except Exception as e:
            logger.error(f"Error getting service health statuses: {e}")

        return services
    
    @staticmethod
    async def _check_postgres_health() -> bool:
        """Check PostgreSQL database health."""
        try:
            return await db.health_check()
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            return False
    
    @staticmethod
    async def _check_redis_health() -> bool:
        """Check Redis cache health."""
        try:
            return await redis_manager.health_check()
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    @staticmethod
    async def _get_postgres_version() -> str:
        """Get PostgreSQL version information."""
        try:
            # This would require a database query to get version info
            # Placeholder implementation
            return "14.x"
        except Exception as e:
            logger.error(f"Failed to get PostgreSQL version: {e}")
            return "unknown"
    
    @staticmethod
    async def _get_postgres_connections() -> int:
        """Get number of active PostgreSQL connections."""
        try:
            # This would require querying pg_stat_activity or connection pool
            # Placeholder implementation
            return 1 if await HealthService._check_postgres_health() else 0
        except Exception as e:
            logger.error(f"Failed to get PostgreSQL connections: {e}")
            return 0
    
    @staticmethod
    async def _get_redis_version() -> str:
        """Get Redis version information."""
        try:
            # This would require Redis INFO command
            # Placeholder implementation
            return "7.x"
        except Exception as e:
            logger.error(f"Failed to get Redis version: {e}")
            return "unknown"
    
    @staticmethod
    async def _get_redis_memory_usage() -> Dict[str, Any]:
        """Get Redis memory usage information."""
        try:
            # This would require Redis INFO memory command
            # Placeholder implementation
            return {
                "used_memory": "1MB",
                "used_memory_peak": "2MB",
                "used_memory_percentage": "50%"
            }
        except Exception as e:
            logger.error(f"Failed to get Redis memory usage: {e}")
            return {"error": str(e)}

    @staticmethod
    async def _check_bloom_filter_health() -> dict:
        """Check bloom filter health."""
        try:
            bloom_filter = DuplicationBloomFilter()
            await bloom_filter.initialize()
            stats = await bloom_filter.get_statistics()

            # Check if filter is working
            implementation = stats.get('implementation', 'Unknown')
            capacity = stats.get('capacity', 0)
            items_inserted = stats.get('number_of_items_inserted', 0)
            hit_rate = stats.get('hit_rate', 0)

            is_healthy = capacity > 0 and implementation != 'Unknown'

            return {
                'status': 'healthy' if is_healthy else 'unhealthy',
                'implementation': implementation,
                'capacity_used': f"{items_inserted:,}",
                'hit_rate': f"{hit_rate:.1%}",
                'last_reset': stats.get('last_reset', 'never'),
                'total_checks': stats.get('total_checks', 0),
                'total_adds': stats.get('total_adds', 0)
            }

        except Exception as e:
            logger.error(f"Bloom filter health check failed: {e}")
            return {
                'status': 'unhealthy',
                'implementation': 'Unknown',
                'error': str(e)
            }