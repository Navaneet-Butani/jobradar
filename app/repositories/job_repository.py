"""Job repository for database operations."""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, text
from sqlalchemy.orm import selectinload

from .base import BaseRepository, CacheableRepositoryMixin
from ..models import JobDB, JobDetailDB, CompanyDB, JobSourceDB
from ..models.job import JobSearchCriteria
from ..models.common import JobStatus
from ..core.database import db

logger = logging.getLogger(__name__)


class JobRepository(BaseRepository[JobDB], CacheableRepositoryMixin):
    """Repository for job-related database operations."""
    
    def __init__(self):
        super().__init__(JobDB)
        CacheableRepositoryMixin.__init__(self, cache_ttl=600)  # 10 minutes

    async def get_job_detail(
        self,
        job_id: int,
        session: Optional[AsyncSession] = None
    ) -> Optional[JobDetailDB]:
        """Fetch the job_details row for a job (description, raw payload, ...)."""
        if session is None:
            session = db.session
        return await session.get(JobDetailDB, job_id)

    async def upsert_job_detail(
        self,
        job_id: int,
        data: Dict[str, Any],
        session: Optional[AsyncSession] = None
    ) -> JobDetailDB:
        """Create or update the job_details row for a job (description, raw payload, ...)."""
        if session is None:
            session = db.session

        try:
            existing = await session.get(JobDetailDB, job_id)
            if existing:
                for key, value in data.items():
                    setattr(existing, key, value)
                await session.commit()
                return existing

            detail = JobDetailDB(job_id=job_id, **data)
            session.add(detail)
            await session.commit()
            return detail
        except Exception as e:
            await session.rollback()
            logger.error(f"Error upserting job_details for job {job_id}: {e}")
            raise


    async def get_by_content_hash(
        self, 
        content_hash: str, 
        session: Optional[AsyncSession] = None
    ) -> Optional[JobDB]:
        """Get job by content hash."""
        if session is None:
            session = db.session
            
        # Check cache first
        cache_key = self._get_cache_key("job_hash", content_hash)
        cached_job = await self._get_from_cache(cache_key)
        if cached_job:
            return cached_job
            
        try:
            result = await session.execute(
                select(JobDB)
                .where(JobDB.content_hash == content_hash)
                .options(selectinload(JobDB.company))
            )
            # content_hash isn't DB-unique — multiple stored jobs can
            # legitimately collide (that's what dedup is for). Any match is
            # enough to flag a duplicate, so take the first.
            job = result.scalars().first()

            if job:
                # Cache the result
                await self._set_cache(cache_key, job)

            return job
        except Exception as e:
            logger.error(f"Error fetching job by content hash {content_hash}: {e}")
            raise
            
    async def get_by_external_id(
        self, 
        source_id: int, 
        external_id: str, 
        session: Optional[AsyncSession] = None
    ) -> Optional[JobDB]:
        """Get job by source and external ID."""
        if session is None:
            session = db.session
            
        try:
            result = await session.execute(
                select(JobDB)
                .where(and_(JobDB.source_id == source_id, JobDB.external_id == external_id))
                .options(selectinload(JobDB.company))
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching job by external ID {source_id}:{external_id}: {e}")
            raise
            
    async def search_jobs(
        self, 
        criteria: JobSearchCriteria, 
        session: Optional[AsyncSession] = None
    ) -> Tuple[List[JobDB], int]:
        """Search jobs with advanced filtering."""
        if session is None:
            session = db.session
            
        try:
            # Build base query
            query = select(JobDB).options(
                selectinload(JobDB.company),
                selectinload(JobDB.employment_type),
                selectinload(JobDB.experience_level),
                selectinload(JobDB.work_arrangement)
            )
            
            # Apply filters
            filters = []
            
            # Text search
            if criteria.query:
                search_term = f"%{criteria.query.lower()}%"
                filters.append(
                    or_(
                        func.lower(JobDB.title).contains(search_term),
                        func.lower(JobDB.normalized_title).contains(search_term)
                    )
                )
                
            # Title filter
            if criteria.title:
                filters.append(func.lower(JobDB.title).contains(criteria.title.lower()))
                
            # Company filter
            if criteria.company:
                company_filter = func.lower(CompanyDB.name).contains(criteria.company.lower())
                query = query.join(CompanyDB, JobDB.company_id == CompanyDB.id)
                filters.append(company_filter)
                
            # Location filter
            if criteria.location:
                location_term = f"%{criteria.location.lower()}%"
                filters.append(
                    or_(
                        func.lower(JobDB.city).contains(location_term),
                        func.lower(JobDB.country).contains(location_term),
                        func.lower(JobDB.location_raw).contains(location_term)
                    )
                )
                
            # Employment type filter
            if criteria.employment_types:
                query = query.join(JobDB.employment_type)
                filters.append(JobDB.employment_type_id.in_([et.value for et in criteria.employment_types]))
                
            # Experience level filter
            if criteria.experience_levels:
                query = query.join(JobDB.experience_level)
                filters.append(JobDB.experience_level_id.in_([el.value for el in criteria.experience_levels]))
                
            # Remote work filter
            if criteria.is_remote is not None:
                filters.append(JobDB.is_remote == criteria.is_remote)
                
            # Salary filters
            if criteria.min_salary:
                filters.append(
                    or_(
                        JobDB.salary_min >= criteria.min_salary,
                        JobDB.salary_max >= criteria.min_salary
                    )
                )
                
            if criteria.max_salary:
                filters.append(
                    and_(
                        JobDB.salary_min <= criteria.max_salary,
                        JobDB.salary_max <= criteria.max_salary
                    )
                )
                
            if criteria.salary_currency:
                filters.append(JobDB.salary_currency == criteria.salary_currency.value)
                
            if criteria.salary_disclosed_only:
                filters.append(JobDB.salary_disclosed == True)
                
            # Skills filters
            if criteria.required_skills:
                skills_filter = []
                for skill in criteria.required_skills:
                    skills_filter.append(
                        or_(
                            func.jsonb_path_exists(JobDB.skills_required, f'$[*] ? (@.name == "{skill}")'),
                            func.jsonb_path_exists(JobDB.skills_extracted, f'$[*] ? (@ == "{skill}")')
                        )
                    )
                filters.append(and_(*skills_filter))
                
            if criteria.preferred_skills:
                skills_filter = []
                for skill in criteria.preferred_skills:
                    skills_filter.append(
                        or_(
                            func.jsonb_path_exists(JobDB.skills_preferred, f'$[*] ? (@.name == "{skill}")'),
                            func.jsonb_path_exists(JobDB.skills_extracted, f'$[*] ? (@ == "{skill}")')
                        )
                    )
                filters.extend(skills_filter)  # OR condition for preferred skills
                
            # Date filters
            if criteria.posted_after:
                filters.append(JobDB.posted_date >= criteria.posted_after)
                
            if criteria.posted_before:
                filters.append(JobDB.posted_date <= criteria.posted_before)
                
            # Quality filters
            if criteria.min_quality_score:
                filters.append(JobDB.quality_score >= criteria.min_quality_score)
                
            if criteria.exclude_spam:
                filters.append(JobDB.spam_score < 70.0)  # Configurable threshold
                
            # Default status filter
            filters.append(JobDB.status == JobStatus.ACTIVE)
            
            # Apply all filters
            if filters:
                query = query.where(and_(*filters))
                
            # Get total count for pagination
            count_query = select(func.count()).select_from(query.subquery())
            total_count = await session.execute(count_query)
            total = total_count.scalar()
            
            # Apply sorting
            if criteria.sort_by == "posted_date":
                if criteria.sort_order == "desc":
                    query = query.order_by(desc(JobDB.posted_date))
                else:
                    query = query.order_by(JobDB.posted_date)
            elif criteria.sort_by == "quality_score":
                if criteria.sort_order == "desc":
                    query = query.order_by(desc(JobDB.quality_score))
                else:
                    query = query.order_by(JobDB.quality_score)
            elif criteria.sort_by == "salary_max":
                if criteria.sort_order == "desc":
                    query = query.order_by(desc(JobDB.salary_max))
                else:
                    query = query.order_by(JobDB.salary_max)
            else:
                # Default sort by posted date descending
                query = query.order_by(desc(JobDB.posted_date))
                
            # Apply pagination
            query = query.offset(criteria.offset).limit(criteria.limit)
            
            # Execute query
            result = await session.execute(query)
            jobs = list(result.scalars().all())
            
            return jobs, total
        except Exception as e:
            logger.error(f"Error searching jobs: {e}")
            raise
            
    async def get_similar_jobs(
        self, 
        job_id: int, 
        limit: int = 10, 
        session: Optional[AsyncSession] = None
    ) -> List[JobDB]:
        """Get similar jobs based on title, company, and skills."""
        if session is None:
            session = db.session
            
        try:
            # Get the reference job
            reference_job = await self.get_by_id(job_id, session)
            if not reference_job:
                return []
                
            # Build similarity query
            query = select(JobDB).where(
                and_(
                    JobDB.id != job_id,
                    JobDB.status == JobStatus.ACTIVE,
                    or_(
                        # Similar title
                        func.similarity(JobDB.normalized_title, reference_job.normalized_title) > 0.3,
                        # Same company
                        JobDB.company_id == reference_job.company_id,
                        # Similar skills (using jsonb operators)
                        func.jsonb_path_exists(
                            JobDB.skills_extracted,
                            '$[*] ? (@ in ({}))'.format(",".join([f'"{s}"' for s in reference_job.skills_extracted]))
                        ) if reference_job.skills_extracted else False
                    )
                )
            ).options(
                selectinload(JobDB.company)
            ).order_by(
                desc(func.similarity(JobDB.normalized_title, reference_job.normalized_title))
            ).limit(limit)
            
            result = await session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error finding similar jobs for {job_id}: {e}")
            raise
            
    async def update_last_seen(
        self, 
        job_id: int, 
        session: Optional[AsyncSession] = None
    ) -> bool:
        """Update last_seen_at timestamp for a job."""
        if session is None:
            session = db.session
            
        try:
            result = await session.execute(
                text("UPDATE jobs SET last_seen_at = NOW() WHERE id = :job_id")
                .bindparams(job_id=job_id)
            )
            await session.commit()
            
            # Invalidate cache
            await self._invalidate_cache(f"job_hash:*")
            
            return result.rowcount > 0
        except Exception as e:
            await session.rollback()
            logger.error(f"Error updating last_seen for job {job_id}: {e}")
            raise
            
    async def mark_expired_jobs(
        self, 
        days_old: int = 60, 
        session: Optional[AsyncSession] = None
    ) -> int:
        """Mark jobs as expired if they haven't been seen for specified days."""
        if session is None:
            session = db.session
            
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            result = await session.execute(
                text("""
                UPDATE jobs 
                SET status = 'expired', updated_at = NOW() 
                WHERE last_seen_at < :cutoff_date 
                AND status = 'active'
                """).bindparams(cutoff_date=cutoff_date)
            )
            await session.commit()
            
            # Invalidate cache
            await self._invalidate_cache("job_*")
            
            logger.info(f"Marked {result.rowcount} jobs as expired")
            return result.rowcount
        except Exception as e:
            await session.rollback()
            logger.error(f"Error marking expired jobs: {e}")
            raise
            
    async def get_jobs_by_company(
        self, 
        company_id: int, 
        status: JobStatus = JobStatus.ACTIVE,
        limit: int = 50,
        session: Optional[AsyncSession] = None
    ) -> List[JobDB]:
        """Get jobs for a specific company."""
        if session is None:
            session = db.session
            
        # Check cache
        cache_key = self._get_cache_key("company_jobs", company_id, status.value)
        cached_jobs = await self._get_from_cache(cache_key)
        if cached_jobs:
            return cached_jobs
            
        try:
            result = await session.execute(
                select(JobDB)
                .where(and_(
                    JobDB.company_id == company_id,
                    JobDB.status == status
                ))
                .options(selectinload(JobDB.employment_type))
                .order_by(desc(JobDB.posted_date))
                .limit(limit)
            )
            jobs = list(result.scalars().all())
            
            # Cache results
            await self._set_cache(cache_key, jobs, ttl=300)  # 5 minutes
            
            return jobs
        except Exception as e:
            logger.error(f"Error fetching jobs for company {company_id}: {e}")
            raise
            
    async def get_job_analytics(
        self, 
        job_id: int, 
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Get analytics data for a specific job."""
        if session is None:
            session = db.session
            
        try:
            result = await session.execute(
                select(
                    JobDB.views_count,
                    JobDB.clicks_count,
                    JobDB.applications_count,
                    JobDB.posted_date,
                    JobDB.first_seen_at
                ).where(JobDB.id == job_id)
            )
            
            row = result.first()
            if not row:
                return {}
                
            analytics = {
                "total_views": row.views_count,
                "total_clicks": row.clicks_count,
                "total_applications": row.applications_count,
                "click_through_rate": row.clicks_count / row.views_count if row.views_count > 0 else 0,
                "application_rate": row.applications_count / row.clicks_count if row.clicks_count > 0 else 0,
                "days_active": (datetime.utcnow() - row.first_seen_at).days if row.first_seen_at else 0
            }
            
            return analytics
        except Exception as e:
            logger.error(f"Error fetching analytics for job {job_id}: {e}")
            raise
            
    async def batch_update_quality_scores(
        self, 
        score_updates: List[Dict[str, Any]], 
        session: Optional[AsyncSession] = None
    ) -> int:
        """Update quality scores for multiple jobs."""
        if session is None:
            session = db.session
            
        try:
            updated_count = 0
            for update in score_updates:
                if 'job_id' not in update or 'quality_score' not in update:
                    continue
                    
                await session.execute(
                    text("""
                    UPDATE jobs 
                    SET quality_score = :quality_score, 
                        spam_score = :spam_score,
                        updated_at = NOW()
                    WHERE id = :job_id
                    """).bindparams(
                        job_id=update['job_id'],
                        quality_score=update['quality_score'],
                        spam_score=update.get('spam_score', 0)
                    )
                )
                updated_count += 1
                
            await session.commit()
            
            # Invalidate cache
            await self._invalidate_cache("job_*")
            
            return updated_count
        except Exception as e:
            await session.rollback()
            logger.error(f"Error batch updating quality scores: {e}")
            raise
            
    async def find_potential_duplicates(
        self, 
        content_hash: str, 
        similarity_threshold: float = 0.8,
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """Find potential duplicate jobs using content hash and similarity."""
        if session is None:
            session = db.session
            
        try:
            # First check for exact hash matches
            exact_matches = await session.execute(
                select(JobDB.id, JobDB.title, JobDB.content_hash)
                .where(JobDB.content_hash == content_hash)
            )
            
            duplicates = []
            for row in exact_matches.all():
                duplicates.append({
                    "job_id": row.id,
                    "title": row.title,
                    "similarity_score": 1.0,
                    "match_type": "exact_hash"
                })
                
            # If no exact matches, look for similar titles and companies
            if not duplicates:
                similar_jobs = await session.execute(
                    text("""
                    SELECT id, title, similarity(title, :reference_title) as sim_score
                    FROM jobs 
                    WHERE similarity(title, :reference_title) > :threshold
                    AND status = 'active'
                    ORDER BY sim_score DESC
                    LIMIT 5
                    """).bindparams(
                        reference_title="", # This would be passed as parameter
                        threshold=similarity_threshold
                    )
                )
                
                for row in similar_jobs.all():
                    duplicates.append({
                        "job_id": row.id,
                        "title": row.title,
                        "similarity_score": float(row.sim_score),
                        "match_type": "title_similarity"
                    })
                    
            return duplicates
        except Exception as e:
            logger.error(f"Error finding potential duplicates: {e}")
            raise

    async def increment_view_count(
        self,
        job_id: int,
        session: Optional[AsyncSession] = None
    ) -> bool:
        """Increment view count for a job."""
        if session is None:
            session = db.session

        try:
            result = await session.execute(
                text("UPDATE jobs SET views_count = views_count + 1 WHERE id = :job_id")
                .bindparams(job_id=job_id)
            )
            await session.commit()

            # Invalidate cache
            await self._invalidate_cache(f"job_*")

            return result.rowcount > 0
        except Exception as e:
            await session.rollback()
            logger.error(f"Error incrementing view count for job {job_id}: {e}")
            raise