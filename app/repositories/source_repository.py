"""Source repository for database operations."""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, text
from sqlalchemy.orm import selectinload

from .base import BaseRepository, CacheableRepositoryMixin
from ..models import JobSourceDB, SourceFetchLogDB
from ..models.source import SourceConfig, SourceStats
from ..core.database import db

logger = logging.getLogger(__name__)


class SourceRepository(BaseRepository[JobSourceDB], CacheableRepositoryMixin):
    """Repository for job source-related database operations."""
    
    def __init__(self):
        super().__init__(JobSourceDB)
        CacheableRepositoryMixin.__init__(self, cache_ttl=1800)  # 30 minutes
        
    async def get_active_sources(
        self, 
        session: Optional[AsyncSession] = None
    ) -> List[JobSourceDB]:
        """Get all active job sources."""
        if session is None:
            session = db.session
            
        cache_key = self._get_cache_key("active_sources")
        cached_sources = await self._get_from_cache(cache_key)
        if cached_sources:
            return cached_sources
            
        try:
            result = await session.execute(
                select(JobSourceDB)
                .where(JobSourceDB.is_active == True)
                .order_by(desc(JobSourceDB.success_rate))
            )
            sources = list(result.scalars().all())
            
            # Cache for 30 minutes
            await self._set_cache(cache_key, sources, ttl=1800)
            
            return sources
        except Exception as e:
            logger.error(f"Error fetching active sources: {e}")
            raise
            
    async def get_source_by_name(
        self, 
        name: str, 
        session: Optional[AsyncSession] = None
    ) -> Optional[JobSourceDB]:
        """Get source by name."""
        if session is None:
            session = db.session
            
        cache_key = self._get_cache_key("source_name", name)
        cached_source = await self._get_from_cache(cache_key)
        if cached_source:
            return cached_source
            
        try:
            result = await session.execute(
                select(JobSourceDB).where(JobSourceDB.name == name)
            )
            source = result.scalar_one_or_none()
            
            if source:
                await self._set_cache(cache_key, source)
                
            return source
        except Exception as e:
            logger.error(f"Error fetching source by name {name}: {e}")
            raise
            
    async def get_source_config(
        self, 
        source_id: int, 
        session: Optional[AsyncSession] = None
    ) -> Optional[SourceConfig]:
        """Get source configuration for processing."""
        if session is None:
            session = db.session
            
        cache_key = self._get_cache_key("source_config", source_id)
        cached_config = await self._get_from_cache(cache_key)
        if cached_config:
            return SourceConfig(**cached_config)
            
        try:
            source = await self.get_by_id(source_id, session)
            if not source:
                return None
                
            config = SourceConfig(
                source_id=source.id,
                name=source.name,
                source_type=source.type,
                base_url=source.base_url,
                is_active=source.is_active,
                api_config=source.api_config,
                scraping_config=source.scraping_config,
                hourly_quota=source.hourly_quota,
                daily_quota=source.daily_quota,
                monthly_quota=source.monthly_quota
            )
            
            # Load field mapping if available
            if source.field_mapping:
                from ..models.source import FieldMapping, ExtractionRules
                config.field_mapping = FieldMapping(**source.field_mapping.get('field_mapping', {}))
                config.extraction_rules = ExtractionRules(**source.field_mapping.get('extraction_rules', {}))
                
            # Cache for 1 hour
            await self._set_cache(cache_key, config.dict(), ttl=3600)
            
            return config
        except Exception as e:
            logger.error(f"Error fetching source config for {source_id}: {e}")
            raise
            
    async def update_source_stats(
        self, 
        source_id: int, 
        stats: Dict[str, Any], 
        session: Optional[AsyncSession] = None
    ) -> bool:
        """Update source statistics."""
        if session is None:
            session = db.session
            
        try:
            update_data = {}
            
            # Update success rate if provided
            if 'success_rate' in stats:
                update_data['success_rate'] = stats['success_rate']
                
            # Update consecutive failures
            if 'consecutive_failures' in stats:
                update_data['consecutive_failures'] = stats['consecutive_failures']
                
            # Update last successful fetch
            if 'last_successful_fetch' in stats:
                update_data['last_successful_fetch'] = stats['last_successful_fetch']
                
            # Update job counts
            if 'jobs_fetched' in stats:
                update_data['total_jobs_fetched'] = JobSourceDB.total_jobs_fetched + stats['jobs_fetched']
                
            if 'jobs_added' in stats:
                update_data['total_jobs_added'] = JobSourceDB.total_jobs_added + stats['jobs_added']
                
            # Update fetch time
            if 'fetch_time_ms' in stats:
                update_data['average_fetch_time_ms'] = stats['fetch_time_ms']
                
            # Update calls made today
            if 'calls_made' in stats:
                update_data['calls_made_today'] = JobSourceDB.calls_made_today + stats['calls_made']
                
            if update_data:
                await session.execute(
                    text("""
                    UPDATE job_sources 
                    SET {}
                    WHERE id = :source_id
                    """.format(
                        ', '.join([f"{k} = :{k}" for k in update_data.keys()] + ["updated_at = NOW()"])
                    )).bindparams(source_id=source_id, **update_data)
                )
                await session.commit()
                
                # Invalidate cache
                await self._invalidate_cache(f"source_*")
                
                return True
                
            return False
        except Exception as e:
            await session.rollback()
            logger.error(f"Error updating source stats for {source_id}: {e}")
            raise
            
    async def check_quota_limits(
        self, 
        source_id: int, 
        session: Optional[AsyncSession] = None
    ) -> Dict[str, bool]:
        """Check if source has exceeded quota limits."""
        if session is None:
            session = db.session
            
        try:
            source = await self.get_by_id(source_id, session)
            if not source:
                return {"can_fetch": False, "reason": "source_not_found"}
                
            # Check daily quota
            if source.calls_made_today >= source.daily_quota:
                return {
                    "can_fetch": False, 
                    "reason": "daily_quota_exceeded",
                    "calls_made": source.calls_made_today,
                    "daily_limit": source.daily_quota
                }
                
            # Check monthly budget
            if source.monthly_spend >= source.monthly_budget:
                return {
                    "can_fetch": False, 
                    "reason": "monthly_budget_exceeded",
                    "spend": float(source.monthly_spend),
                    "budget": float(source.monthly_budget)
                }
                
            # Check consecutive failures
            if source.consecutive_failures >= 5:  # Configurable threshold
                return {
                    "can_fetch": False, 
                    "reason": "too_many_failures",
                    "failures": source.consecutive_failures
                }
                
            return {
                "can_fetch": True,
                "remaining_calls": source.daily_quota - source.calls_made_today,
                "remaining_budget": float(source.monthly_budget - source.monthly_spend)
            }
        except Exception as e:
            logger.error(f"Error checking quota limits for source {source_id}: {e}")
            raise
            
    async def reset_daily_counters(
        self, 
        session: Optional[AsyncSession] = None
    ) -> int:
        """Reset daily counters for all sources (called daily via cron)."""
        if session is None:
            session = db.session
            
        try:
            result = await session.execute(
                text("""
                UPDATE job_sources 
                SET calls_made_today = 0, updated_at = NOW()
                WHERE calls_made_today > 0
                """)
            )
            await session.commit()
            
            # Invalidate cache
            await self._invalidate_cache("source_*")
            
            logger.info(f"Reset daily counters for {result.rowcount} sources")
            return result.rowcount
        except Exception as e:
            await session.rollback()
            logger.error(f"Error resetting daily counters: {e}")
            raise
            
    async def get_source_performance(
        self, 
        source_id: int, 
        days: int = 30,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Get performance metrics for a source over specified days."""
        if session is None:
            session = db.session
            
        try:
            # Get basic source info
            source = await self.get_by_id(source_id, session)
            if not source:
                return {}
                
            # Get fetch logs for the period
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            logs_result = await session.execute(
                select(
                    func.count(SourceFetchLogDB.id).label('total_fetches'),
                    func.sum(SourceFetchLogDB.jobs_fetched).label('total_jobs_fetched'),
                    func.sum(SourceFetchLogDB.jobs_added).label('total_jobs_added'),
                    func.sum(SourceFetchLogDB.errors_count).label('total_errors'),
                    func.avg(SourceFetchLogDB.execution_time_ms).label('avg_execution_time'),
                    func.count(
                        func.case([(SourceFetchLogDB.status == 'completed', 1)], else_=None)
                    ).label('successful_fetches')
                ).where(
                    and_(
                        SourceFetchLogDB.source_id == source_id,
                        SourceFetchLogDB.started_at >= cutoff_date
                    )
                )
            )
            
            row = logs_result.first()
            
            # Calculate success rate
            success_rate = 0
            if row.total_fetches and row.total_fetches > 0:
                success_rate = (row.successful_fetches / row.total_fetches) * 100
                
            # Calculate job add rate
            add_rate = 0
            if row.total_jobs_fetched and row.total_jobs_fetched > 0:
                add_rate = (row.total_jobs_added / row.total_jobs_fetched) * 100
                
            performance = {
                "source_id": source_id,
                "source_name": source.name,
                "period_days": days,
                "total_fetches": row.total_fetches or 0,
                "successful_fetches": row.successful_fetches or 0,
                "success_rate_percent": round(success_rate, 2),
                "total_jobs_fetched": row.total_jobs_fetched or 0,
                "total_jobs_added": row.total_jobs_added or 0,
                "job_add_rate_percent": round(add_rate, 2),
                "total_errors": row.total_errors or 0,
                "avg_execution_time_ms": int(row.avg_execution_time) if row.avg_execution_time else 0,
                "current_status": {
                    "is_active": source.is_active,
                    "consecutive_failures": source.consecutive_failures,
                    "calls_made_today": source.calls_made_today,
                    "daily_quota": source.daily_quota,
                    "monthly_spend": float(source.monthly_spend),
                    "monthly_budget": float(source.monthly_budget)
                }
            }
            
            return performance
        except Exception as e:
            logger.error(f"Error fetching source performance for {source_id}: {e}")
            raise
            
    async def get_all_source_stats(
        self, 
        session: Optional[AsyncSession] = None
    ) -> List[SourceStats]:
        """Get statistics for all sources."""
        if session is None:
            session = db.session
            
        cache_key = self._get_cache_key("all_source_stats")
        cached_stats = await self._get_from_cache(cache_key)
        if cached_stats:
            return [SourceStats(**stats) for stats in cached_stats]
            
        try:
            result = await session.execute(
                select(JobSourceDB).order_by(desc(JobSourceDB.success_rate))
            )
            sources = result.scalars().all()
            
            stats_list = []
            for source in sources:
                stats = SourceStats(
                    source_id=source.id,
                    success_rate=float(source.success_rate),
                    consecutive_failures=source.consecutive_failures,
                    last_successful_fetch=source.last_successful_fetch,
                    total_jobs_fetched=source.total_jobs_fetched,
                    total_jobs_added=source.total_jobs_added,
                    average_fetch_time_ms=source.average_fetch_time_ms,
                    cost_per_call=source.cost_per_call,
                    monthly_spend=source.monthly_spend,
                    calls_made_today=source.calls_made_today
                )
                stats_list.append(stats)
                
            # Cache for 15 minutes
            await self._set_cache(cache_key, [stats.dict() for stats in stats_list], ttl=900)
            
            return stats_list
        except Exception as e:
            logger.error(f"Error fetching all source stats: {e}")
            raise
            
    async def update_field_mapping(
        self, 
        source_id: int, 
        field_mapping: Dict[str, Any], 
        session: Optional[AsyncSession] = None
    ) -> bool:
        """Update field mapping configuration for a source."""
        if session is None:
            session = db.session
            
        try:
            await session.execute(
                text("""
                UPDATE job_sources 
                SET field_mapping = :field_mapping,
                    updated_at = NOW()
                WHERE id = :source_id
                """).bindparams(
                    source_id=source_id,
                    field_mapping=field_mapping
                )
            )
            await session.commit()
            
            # Invalidate cache
            await self._invalidate_cache(f"source_*")
            
            return True
        except Exception as e:
            await session.rollback()
            logger.error(f"Error updating field mapping for source {source_id}: {e}")
            raise
            
    async def deactivate_failed_sources(
        self, 
        failure_threshold: int = 10,
        session: Optional[AsyncSession] = None
    ) -> int:
        """Deactivate sources with too many consecutive failures."""
        if session is None:
            session = db.session
            
        try:
            result = await session.execute(
                text("""
                UPDATE job_sources 
                SET is_active = false, updated_at = NOW()
                WHERE consecutive_failures >= :threshold
                AND is_active = true
                """).bindparams(threshold=failure_threshold)
            )
            await session.commit()
            
            # Invalidate cache
            await self._invalidate_cache("source_*")
            
            if result.rowcount > 0:
                logger.warning(f"Deactivated {result.rowcount} sources due to excessive failures")
                
            return result.rowcount
        except Exception as e:
            await session.rollback()
            logger.error(f"Error deactivating failed sources: {e}")
            raise