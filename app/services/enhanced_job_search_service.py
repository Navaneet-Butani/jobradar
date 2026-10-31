"""Enhanced job search service using the new query builder and full-text search."""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..core.database import db
from ..core.redis import redis_manager
from ..models import JobDB
from ..models.job import JobSearchCriteria
from ..models.common import JobStatus
from .search.query_builder import SearchQueryBuilder
from .search.facet_service import FacetService

logger = logging.getLogger(__name__)


def _iso(value) -> Optional[str]:
    """Datetime to ISO string, tolerating None and already-stringified values."""
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _float(value) -> Optional[float]:
    """Numeric column to float — Decimal does not survive JSON serialization."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class EnhancedJobSearchService:
    """Enhanced job search service with full-text search and faceted search."""

    def __init__(self):
        self.cache_prefix = "enhanced_job_search"
        self.cache_ttl = 300  # 5 minutes
        self.facet_service = FacetService()

    async def search_jobs(
        self,
        criteria: JobSearchCriteria,
        user_id: Optional[int] = None,
        session: Optional[AsyncSession] = None,
        include_facets: bool = False
    ) -> Dict[str, Any]:
        """
        Enhanced job search with full-text search and optional facets.

        Args:
            criteria: Search criteria and filters
            user_id: Optional user ID for personalization
            session: Optional database session
            include_facets: Whether to include faceted search results

        Returns:
            Dict with jobs, total count, metadata, and optional facets
        """
        try:
            if session is None:
                session = db.session

            # Generate cache key
            cache_key = self._generate_cache_key(criteria, user_id, include_facets)

            # Try cache first
            cached_result = await self._get_from_cache(cache_key)
            if cached_result:
                logger.info(f"Enhanced search cache hit: {criteria.query}")
                return cached_result

            # Track search analytics
            await self._track_search_query(criteria, user_id)

            # Build query using new query builder
            start_time = datetime.utcnow()
            query_builder = SearchQueryBuilder.from_criteria(criteria)

            # Execute search query
            search_query, search_params = query_builder.build_select_query(include_details=True)
            count_query, count_params = query_builder.build_count_query()

            # Execute queries in parallel
            search_result = await session.execute(text(search_query), search_params)
            count_result = await session.execute(text(count_query), count_params)

            jobs_data = search_result.fetchall()
            total_count = count_result.scalar()
            search_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Convert database rows to job objects
            enhanced_jobs = await self._convert_db_rows_to_jobs(jobs_data, user_id, session)

            # Build response
            result = {
                "jobs": enhanced_jobs,
                "total": total_count,
                "page": (criteria.offset // criteria.limit) + 1,
                "limit": criteria.limit,
                "pages": (total_count + criteria.limit - 1) // criteria.limit,
                "query_time_ms": search_time_ms,
                "filters_applied": self._get_applied_filters(criteria),
                "has_next": (criteria.offset + criteria.limit) < total_count,
                "has_previous": criteria.offset > 0,
                "search_type": "enhanced_fts"  # Indicate this is full-text search
            }

            # Add facets if requested
            if include_facets:
                facet_start = datetime.utcnow()
                result["facets"] = await self.facet_service.calculate_facets(criteria, session)
                facet_time_ms = int((datetime.utcnow() - facet_start).total_seconds() * 1000)
                result["facet_time_ms"] = facet_time_ms

            # Cache the result
            await self._set_cache(cache_key, result, self.cache_ttl)

            logger.info(f"Enhanced search completed: {len(enhanced_jobs)} jobs found in {search_time_ms}ms")
            return result

        except Exception as e:
            logger.error(f"Error in enhanced job search: {e}")
            raise

    async def get_job_details(
        self,
        job_id: int,
        user_id: Optional[int] = None,
        session: Optional[AsyncSession] = None
    ) -> Optional[Dict[str, Any]]:
        """Get detailed job information using the enhanced query builder."""
        try:
            if session is None:
                session = db.session

            # Build query for single job with all details
            query = """
                SELECT
                    j.id, j.uuid, j.title, j.normalized_title,
                    j.company_id, j.location_raw, j.city, j.state_province,
                    j.country, j.is_remote, j.employment_type_id,
                    j.experience_level_id, j.work_arrangement_id,
                    j.salary_min, j.salary_max, j.salary_currency,
                    j.salary_disclosed, j.apply_url, j.skills_required,
                    j.skills_preferred, j.posted_date, j.first_seen_at,
                    j.last_seen_at, j.remote_scope, j.min_exp_years, j.max_exp_years,
                    j.department, j.source_url, j.apply_email, j.application_deadline,
                    j.quality_score, j.views_count, j.clicks_count,
                    j.poster_name, j.poster_title,
                    j.source_applicant_count, j.source_view_count,
                    c.name as company_name, c.logo_url as company_logo,
                    c.website as company_website, c.industry as company_industry,
                    c.headquarters as company_headquarters, c.ats_type as company_ats_type,
                    c.slug as company_slug, c.tagline as company_tagline,
                    c.description as company_description, c.founded_year as company_founded_year,
                    c.employee_count as company_employee_count,
                    c.employee_range as company_employee_range,
                    c.rating as company_rating, c.rating_count as company_rating_count,
                    c.rating_url as company_rating_url, c.rating_source as company_rating_source,
                    s.name as source_name,
                    jd.description, jd.requirements, jd.responsibilities,
                    jd.company_benefits, jd.how_to_apply,
                    et.name as employment_type_name,
                    el.name as experience_level_name,
                    wa.name as work_arrangement_name
                FROM jobs j
                LEFT JOIN companies c ON j.company_id = c.id
                LEFT JOIN job_sources s ON j.source_id = s.id
                LEFT JOIN job_details jd ON j.id = jd.job_id
                LEFT JOIN employment_types et ON j.employment_type_id = et.id
                LEFT JOIN experience_levels el ON j.experience_level_id = el.id
                LEFT JOIN work_arrangements wa ON j.work_arrangement_id = wa.id
                WHERE j.id = :job_id AND j.status = 'active'
            """

            result = await session.execute(text(query), {"job_id": job_id})
            job_row = result.fetchone()

            if not job_row:
                return None

            # Track job view
            await self._track_job_view(job_id, user_id)

            # Convert to enhanced job format
            enhanced_job = await self._convert_single_row_to_job(job_row, user_id, session)

            return enhanced_job

        except Exception as e:
            logger.error(f"Error getting enhanced job details for {job_id}: {e}")
            raise

    async def get_similar_jobs(
        self,
        job_id: int,
        limit: int = 10,
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """Get similar jobs using enhanced search capabilities."""
        try:
            if session is None:
                session = db.session

            # First get the reference job
            reference_job = await self.get_job_details(job_id, session=session)
            if not reference_job:
                return []

            # Build similarity criteria
            criteria = JobSearchCriteria(
                query=reference_job["title"],  # Use title for text similarity
                company=reference_job["company"]["name"] if reference_job["company"]["name"] != "Unknown" else None,
                employment_types=None,  # Don't filter by employment type for more results
                limit=limit + 5,  # Get a few extra to filter out the original
                offset=0,
                sort_by="relevance",
                sort_order="desc"
            )

            # Search for similar jobs
            similar_results = await self.search_jobs(criteria, session=session)

            # Filter out the original job and limit results
            similar_jobs = [
                job for job in similar_results["jobs"]
                if job["id"] != job_id
            ][:limit]

            return similar_jobs

        except Exception as e:
            logger.error(f"Error finding similar jobs for {job_id}: {e}")
            return []

    async def get_autocomplete_suggestions(
        self,
        query: str,
        suggestion_type: str = "all",
        limit: int = 10,
        session: Optional[AsyncSession] = None
    ) -> List[str]:
        """Enhanced autocomplete with database-driven suggestions."""
        try:
            if session is None:
                session = db.session

            cache_key = f"{self.cache_prefix}:autocomplete:{suggestion_type}:{query.lower()}"

            # Check cache first
            cached_result = await self._get_from_cache(cache_key)
            if cached_result:
                return cached_result

            suggestions = []

            if suggestion_type in ["all", "title"]:
                title_suggestions = await self._get_db_title_suggestions(query, limit // 2, session)
                suggestions.extend(title_suggestions)

            if suggestion_type in ["all", "company"]:
                company_suggestions = await self._get_db_company_suggestions(query, limit // 2, session)
                suggestions.extend(company_suggestions)

            if suggestion_type in ["all", "location"]:
                location_suggestions = await self._get_db_location_suggestions(query, limit // 2, session)
                suggestions.extend(location_suggestions)

            if suggestion_type in ["all", "skills"]:
                skills_suggestions = await self._get_db_skills_suggestions(query, limit // 2, session)
                suggestions.extend(skills_suggestions)

            # Remove duplicates and limit
            unique_suggestions = list(dict.fromkeys(suggestions))[:limit]

            # Cache for 1 hour
            await self._set_cache(cache_key, unique_suggestions, 3600)

            return unique_suggestions

        except Exception as e:
            logger.error(f"Error getting enhanced autocomplete suggestions: {e}")
            return []

    # Private methods

    async def _convert_db_rows_to_jobs(
        self,
        rows: List[Any],
        user_id: Optional[int],
        session: AsyncSession = None
    ) -> List[Dict[str, Any]]:
        """Convert database rows to enhanced job format."""
        jobs = []
        for row in rows:
            job = await self._convert_single_row_to_job(row, user_id, session)
            jobs.append(job)
        return jobs

    @staticmethod
    def _skill_names(skills: Optional[List[Any]]) -> List[str]:
        """Normalize stored skills (plain strings or SkillInfo dicts) to name strings."""
        if not skills:
            return []
        return [s["name"] if isinstance(s, dict) else s for s in skills]

    async def _convert_single_row_to_job(
        self,
        row: Any,
        user_id: Optional[int],
        session: AsyncSession = None
    ) -> Dict[str, Any]:
        """Convert single database row to enhanced job format."""
        job_data = {
            "id": row.id,
            "uuid": str(row.uuid),
            "title": row.title,
            "normalized_title": getattr(row, 'normalized_title', None),
            "company": {
                "id": row.company_id,
                "name": getattr(row, 'company_name', None) or 'Unknown',
                "slug": getattr(row, 'company_slug', None),
                "logo_url": getattr(row, 'company_logo', None),
                "website": getattr(row, 'company_website', None),
                "industry": getattr(row, 'company_industry', None),
                "headquarters": getattr(row, 'company_headquarters', None),
                "ats_type": getattr(row, 'company_ats_type', None),
                "tagline": getattr(row, 'company_tagline', None),
                "description": getattr(row, 'company_description', None),
                "founded_year": getattr(row, 'company_founded_year', None),
                "employee_count": getattr(row, 'company_employee_count', None),
                "employee_range": getattr(row, 'company_employee_range', None),
                "rating": _float(getattr(row, 'company_rating', None)),
                "rating_count": getattr(row, 'company_rating_count', None),
                "rating_url": getattr(row, 'company_rating_url', None),
                "rating_source": getattr(row, 'company_rating_source', None),
            },
            "location": {
                "raw": row.location_raw,
                "city": row.city,
                "state_province": getattr(row, 'state_province', None),
                "country": row.country,
                "is_remote": row.is_remote
            },
            "employment_type": getattr(row, 'employment_type_name', None),
            "experience_level": getattr(row, 'experience_level_name', None),
            "work_arrangement": getattr(row, 'work_arrangement_name', None),
            "salary": {
                "min": float(row.salary_min) if row.salary_min else None,
                "max": float(row.salary_max) if row.salary_max else None,
                "currency": row.salary_currency,
                "disclosed": row.salary_disclosed
            },
            "posted_date": row.posted_date.isoformat() if row.posted_date else None,
            # Provenance: where this came from and when we saw it. `posted_date`
            # is the employer's claim; `first_seen_at` is when it actually
            # reached us, and the two often disagree by days on aggregators.
            "first_seen_at": _iso(getattr(row, 'first_seen_at', None)),
            "last_seen_at": _iso(getattr(row, 'last_seen_at', None)),
            "source_name": getattr(row, 'source_name', None),
            "source_url": getattr(row, 'source_url', None),
            "remote_scope": getattr(row, 'remote_scope', None),
            "min_exp_years": getattr(row, 'min_exp_years', None),
            "max_exp_years": getattr(row, 'max_exp_years', None),
            "department": getattr(row, 'department', None),
            # Who posted it, and how much company the job already has. Both come
            # from the source board, not from us — see raw_backfill.py.
            "poster_name": getattr(row, 'poster_name', None),
            "poster_title": getattr(row, 'poster_title', None),
            "source_applicant_count": getattr(row, 'source_applicant_count', None),
            "source_view_count": getattr(row, 'source_view_count', None),
            "apply_email": getattr(row, 'apply_email', None),
            "application_deadline": _iso(getattr(row, 'application_deadline', None)),
            "apply_url": row.apply_url,
            "skills_required": self._skill_names(row.skills_required),
            "skills_preferred": self._skill_names(row.skills_preferred),
            "quality_score": float(row.quality_score),
            "views_count": row.views_count,
            "clicks_count": getattr(row, 'clicks_count', 0),
            "is_saved": False,  # TODO: Check if user saved this job
            "relevance_score": getattr(row, 'text_relevance_score', None)
        }

        # Add detailed fields if available
        if hasattr(row, 'description'):
            job_data.update({
                "description": getattr(row, 'description', None),
                "requirements": getattr(row, 'requirements', None),
                "responsibilities": getattr(row, 'responsibilities', None),
                "company_benefits": getattr(row, 'company_benefits', None),
                "how_to_apply": getattr(row, 'how_to_apply', None),
            })

        return job_data

    async def _get_db_title_suggestions(
        self,
        query: str,
        limit: int,
        session: AsyncSession = None
    ) -> List[str]:
        """Get title suggestions from database."""
        sql_query = """
            SELECT DISTINCT normalized_title
            FROM jobs
            WHERE normalized_title ILIKE :query_pattern
              AND status = 'active'
              AND normalized_title IS NOT NULL
            ORDER BY normalized_title
            LIMIT :limit
        """

        result = await session.execute(
            text(sql_query),
            {"query_pattern": f"%{query}%", "limit": limit}
        )

        return [row.normalized_title for row in result.fetchall()]

    async def _get_db_company_suggestions(
        self,
        query: str,
        limit: int,
        session: AsyncSession = None
    ) -> List[str]:
        """Get company suggestions from database."""
        sql_query = """
            SELECT DISTINCT c.name
            FROM companies c
            JOIN jobs j ON c.id = j.company_id
            WHERE c.name ILIKE :query_pattern
              AND j.status = 'active'
            ORDER BY c.name
            LIMIT :limit
        """

        result = await session.execute(
            text(sql_query),
            {"query_pattern": f"%{query}%", "limit": limit}
        )

        return [row.name for row in result.fetchall()]

    async def _get_db_location_suggestions(
        self,
        query: str,
        limit: int,
        session: AsyncSession = None
    ) -> List[str]:
        """Get location suggestions from database."""
        sql_query = """
            SELECT DISTINCT
                CASE
                    WHEN city IS NOT NULL AND country IS NOT NULL THEN
                        CONCAT(city, ', ', country)
                    WHEN country IS NOT NULL THEN country
                    ELSE 'Remote'
                END as location
            FROM jobs
            WHERE (city ILIKE :query_pattern OR country ILIKE :query_pattern OR :query_pattern ILIKE '%remote%')
              AND status = 'active'
            ORDER BY location
            LIMIT :limit
        """

        result = await session.execute(
            text(sql_query),
            {"query_pattern": f"%{query}%", "limit": limit}
        )

        return [row.location for row in result.fetchall()]

    async def _get_db_skills_suggestions(
        self,
        query: str,
        limit: int,
        session: AsyncSession = None
    ) -> List[str]:
        """Get skills suggestions from database."""
        sql_query = """
            SELECT DISTINCT skill
            FROM (
                SELECT jsonb_array_elements_text(skills_required) as skill
                FROM jobs
                WHERE status = 'active'
                UNION
                SELECT jsonb_array_elements_text(skills_preferred) as skill
                FROM jobs
                WHERE status = 'active'
            ) skills_data
            WHERE skill ILIKE :query_pattern
              AND LENGTH(skill) > 2
            ORDER BY skill
            LIMIT :limit
        """

        result = await session.execute(
            text(sql_query),
            {"query_pattern": f"%{query}%", "limit": limit}
        )

        return [row.skill for row in result.fetchall()]

    def _generate_cache_key(
        self,
        criteria: JobSearchCriteria,
        user_id: Optional[int],
        include_facets: bool
    ) -> str:
        """Generate cache key for enhanced search."""
        key_data = {
            "query": criteria.query,
            "title": criteria.title,
            "location": criteria.location,
            "company": criteria.company,
            "employment_types": [et.value for et in criteria.employment_types] if criteria.employment_types else None,
            "experience_levels": [el.value for el in criteria.experience_levels] if criteria.experience_levels else None,
            "is_remote": criteria.is_remote,
            "min_salary": str(criteria.min_salary) if criteria.min_salary else None,
            "max_salary": str(criteria.max_salary) if criteria.max_salary else None,
            "limit": criteria.limit,
            "offset": criteria.offset,
            "sort_by": criteria.sort_by,
            "sort_order": criteria.sort_order,
            "user_id": user_id,
            "include_facets": include_facets,
            "search_type": "enhanced"
        }

        key_string = json.dumps(key_data, sort_keys=True)
        import hashlib
        key_hash = hashlib.md5(key_string.encode()).hexdigest()

        return f"{self.cache_prefix}:search:{key_hash}"

    async def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """Get data from Redis cache."""
        try:
            cached_data = await redis_manager.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
        return None

    async def _set_cache(self, cache_key: str, data: Any, ttl: int):
        """Set data in Redis cache."""
        try:
            await redis_manager.set(cache_key, json.dumps(data, default=str), ttl)
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    def _get_applied_filters(self, criteria: JobSearchCriteria) -> List[str]:
        """Get list of applied filters for response metadata."""
        filters = []

        if criteria.query:
            filters.append("text_search")
        if criteria.title:
            filters.append("title_search")
        if criteria.location:
            filters.append("location")
        if criteria.company:
            filters.append("company")
        if criteria.employment_types:
            filters.append("employment_type")
        if criteria.experience_levels:
            filters.append("experience_level")
        if criteria.is_remote is not None:
            filters.append("remote")
        if criteria.min_salary or criteria.max_salary:
            filters.append("salary")
        if criteria.required_skills:
            filters.append("required_skills")
        if criteria.posted_after or criteria.posted_before:
            filters.append("date_range")

        return filters

    async def _track_search_query(self, criteria: JobSearchCriteria, user_id: Optional[int]):
        """Track search query for analytics."""
        try:
            analytics_data = {
                "query": criteria.query,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "filters": self._get_applied_filters(criteria),
                "search_type": "enhanced_fts"
            }

            analytics_key = f"analytics:enhanced_search:{datetime.utcnow().strftime('%Y-%m-%d')}"
            await redis_manager.lpush(analytics_key, json.dumps(analytics_data))

        except Exception as e:
            logger.warning(f"Error tracking enhanced search query: {e}")

    async def _track_job_view(self, job_id: int, user_id: Optional[int]):
        """Track job view for analytics."""
        try:
            # Update view count in database
            if db.session:
                await db.session.execute(
                    text("UPDATE jobs SET views_count = views_count + 1 WHERE id = :job_id"),
                    {"job_id": job_id}
                )
                await db.session.commit()

            # Track in analytics
            analytics_data = {
                "job_id": job_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "action": "view",
                "source": "enhanced_search"
            }

            analytics_key = f"analytics:job_views:{datetime.utcnow().strftime('%Y-%m-%d')}"
            await redis_manager.lpush(analytics_key, json.dumps(analytics_data))

        except Exception as e:
            logger.warning(f"Error tracking enhanced job view: {e}")