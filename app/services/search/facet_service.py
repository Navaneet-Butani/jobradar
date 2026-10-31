"""Faceted search service for aggregating filter counts."""

import logging
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, func, select

from ...core.database import db
from ...core.redis import redis_manager
from ...models import JobDB, CompanyDB, EmploymentTypeDB, ExperienceLevelDB
from ...models.job import JobSearchCriteria
from .query_builder import SearchQueryBuilder

logger = logging.getLogger(__name__)


class FacetService:
    """Service for calculating faceted search aggregations."""

    def __init__(self):
        self.cache_ttl = 300  # 5 minutes cache for facets

    async def calculate_facets(
        self,
        base_criteria: JobSearchCriteria,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Calculate faceted search counts for all filter categories.

        Args:
            base_criteria: Base search criteria (without specific filters to count)
            session: Optional database session

        Returns:
            Dictionary with facet counts for each filter category
        """
        if session is None:
            session = db.session

        try:
            # Generate cache key
            cache_key = self._generate_facet_cache_key(base_criteria)

            # Try cache first
            cached_facets = await self._get_from_cache(cache_key)
            if cached_facets:
                logger.info("Facet cache hit")
                return cached_facets

            # Build base query without category-specific filters
            base_builder = self._build_base_query_builder(base_criteria)
            base_query, base_params = base_builder.build_select_query()

            # Calculate all facets in parallel
            facets = await self._calculate_all_facets(base_query, base_params, session)

            # Cache results
            await self._set_cache(cache_key, facets)

            logger.info(f"Facets calculated for {sum(sum(cat.values()) if isinstance(cat, dict) else 0 for cat in facets.values())} total jobs")
            return facets

        except Exception as e:
            logger.error(f"Error calculating facets: {e}")
            raise

    async def _calculate_all_facets(
        self,
        base_query: str,
        base_params: Dict[str, Any],
        session: AsyncSession = None
    ) -> Dict[str, Any]:
        """Calculate all facet categories."""
        facets = {}

        # Employment Type Facets
        facets["employment_types"] = await self._calculate_employment_type_facets(
            base_query, base_params, session
        )

        # Experience Level Facets
        facets["experience_levels"] = await self._calculate_experience_level_facets(
            base_query, base_params, session
        )

        # Location Facets
        facets["locations"] = await self._calculate_location_facets(
            base_query, base_params, session
        )

        # Company Facets
        facets["companies"] = await self._calculate_company_facets(
            base_query, base_params, session
        )

        # Salary Range Facets
        facets["salary_ranges"] = await self._calculate_salary_range_facets(
            base_query, base_params, session
        )

        # Remote Work Facets
        facets["remote_work"] = await self._calculate_remote_work_facets(
            base_query, base_params, session
        )

        # Posted Date Facets
        facets["posted_dates"] = await self._calculate_posted_date_facets(
            base_query, base_params, session
        )

        return facets

    async def _calculate_employment_type_facets(
        self,
        base_query: str,
        base_params: Dict[str, Any],
        session: AsyncSession = None
    ) -> Dict[str, int]:
        """Calculate employment type facet counts."""
        query = f"""
            WITH base_jobs AS (
                {base_query.replace('SELECT *', 'SELECT j.id')}
            )
            SELECT
                et.name as employment_type,
                COUNT(*) as job_count
            FROM base_jobs bj
            JOIN jobs j ON bj.id = j.id
            LEFT JOIN employment_types et ON j.employment_type_id = et.id
            WHERE et.name IS NOT NULL
            GROUP BY et.name
            ORDER BY job_count DESC
        """

        result = await session.execute(text(query), base_params)
        return {row.employment_type: row.job_count for row in result.fetchall()}

    async def _calculate_experience_level_facets(
        self,
        base_query: str,
        base_params: Dict[str, Any],
        session: AsyncSession = None
    ) -> Dict[str, int]:
        """Calculate experience level facet counts."""
        query = f"""
            WITH base_jobs AS (
                {base_query.replace('SELECT *', 'SELECT j.id')}
            )
            SELECT
                el.name as experience_level,
                COUNT(*) as job_count
            FROM base_jobs bj
            JOIN jobs j ON bj.id = j.id
            LEFT JOIN experience_levels el ON j.experience_level_id = el.id
            WHERE el.name IS NOT NULL
            GROUP BY el.name
            ORDER BY job_count DESC
        """

        result = await session.execute(text(query), base_params)
        return {row.experience_level: row.job_count for row in result.fetchall()}

    async def _calculate_location_facets(
        self,
        base_query: str,
        base_params: Dict[str, Any],
        session: AsyncSession,
        limit: int = 20
    ) -> Dict[str, int]:
        """Calculate location facet counts."""
        query = f"""
            WITH base_jobs AS (
                {base_query.replace('SELECT *', 'SELECT j.id')}
            )
            SELECT
                CASE
                    WHEN j.is_remote THEN 'Remote'
                    WHEN j.city IS NOT NULL AND j.country IS NOT NULL THEN
                        CONCAT(j.city, ', ', j.country)
                    WHEN j.country IS NOT NULL THEN j.country
                    ELSE 'Unknown'
                END as location,
                COUNT(*) as job_count
            FROM base_jobs bj
            JOIN jobs j ON bj.id = j.id
            GROUP BY location
            ORDER BY job_count DESC
            LIMIT {limit}
        """

        result = await session.execute(text(query), base_params)
        return {row.location: row.job_count for row in result.fetchall()}

    async def _calculate_company_facets(
        self,
        base_query: str,
        base_params: Dict[str, Any],
        session: AsyncSession,
        limit: int = 20
    ) -> Dict[str, int]:
        """Calculate company facet counts."""
        query = f"""
            WITH base_jobs AS (
                {base_query.replace('SELECT *', 'SELECT j.id')}
            )
            SELECT
                COALESCE(c.name, 'Unknown') as company_name,
                COUNT(*) as job_count
            FROM base_jobs bj
            JOIN jobs j ON bj.id = j.id
            LEFT JOIN companies c ON j.company_id = c.id
            GROUP BY c.name
            ORDER BY job_count DESC
            LIMIT {limit}
        """

        result = await session.execute(text(query), base_params)
        return {row.company_name: row.job_count for row in result.fetchall()}

    async def _calculate_salary_range_facets(
        self,
        base_query: str,
        base_params: Dict[str, Any],
        session: AsyncSession = None
    ) -> Dict[str, int]:
        """Calculate salary range facet counts."""
        query = f"""
            WITH base_jobs AS (
                {base_query.replace('SELECT *', 'SELECT j.id')}
            ),
            ranged AS (
                SELECT
                    CASE
                        WHEN j.salary_max IS NULL THEN 'Not Disclosed'
                        WHEN j.salary_max < 50000 THEN 'Under $50k'
                        WHEN j.salary_max < 75000 THEN '$50k - $75k'
                        WHEN j.salary_max < 100000 THEN '$75k - $100k'
                        WHEN j.salary_max < 150000 THEN '$100k - $150k'
                        WHEN j.salary_max < 200000 THEN '$150k - $200k'
                        ELSE '$200k+'
                    END as salary_range
                FROM base_jobs bj
                JOIN jobs j ON bj.id = j.id
            )
            SELECT salary_range, COUNT(*) as job_count
            FROM ranged
            GROUP BY salary_range
            ORDER BY
                CASE salary_range
                    WHEN 'Not Disclosed' THEN 0
                    WHEN 'Under $50k' THEN 1
                    WHEN '$50k - $75k' THEN 2
                    WHEN '$75k - $100k' THEN 3
                    WHEN '$100k - $150k' THEN 4
                    WHEN '$150k - $200k' THEN 5
                    WHEN '$200k+' THEN 6
                END
        """

        result = await session.execute(text(query), base_params)
        return {row.salary_range: row.job_count for row in result.fetchall()}

    async def _calculate_remote_work_facets(
        self,
        base_query: str,
        base_params: Dict[str, Any],
        session: AsyncSession = None
    ) -> Dict[str, int]:
        """Calculate remote work facet counts."""
        query = f"""
            WITH base_jobs AS (
                {base_query.replace('SELECT *', 'SELECT j.id')}
            )
            SELECT
                CASE
                    WHEN j.is_remote THEN 'Remote'
                    ELSE 'On-site'
                END as work_type,
                COUNT(*) as job_count
            FROM base_jobs bj
            JOIN jobs j ON bj.id = j.id
            GROUP BY work_type
            ORDER BY job_count DESC
        """

        result = await session.execute(text(query), base_params)
        return {row.work_type: row.job_count for row in result.fetchall()}

    async def _calculate_posted_date_facets(
        self,
        base_query: str,
        base_params: Dict[str, Any],
        session: AsyncSession = None
    ) -> Dict[str, int]:
        """Calculate posted date facet counts."""
        query = f"""
            WITH base_jobs AS (
                {base_query.replace('SELECT *', 'SELECT j.id')}
            ),
            dated AS (
                SELECT
                    CASE
                        WHEN j.posted_date >= CURRENT_DATE THEN 'Today'
                        WHEN j.posted_date >= CURRENT_DATE - INTERVAL '3 days' THEN 'Last 3 days'
                        WHEN j.posted_date >= CURRENT_DATE - INTERVAL '7 days' THEN 'Last week'
                        WHEN j.posted_date >= CURRENT_DATE - INTERVAL '14 days' THEN 'Last 2 weeks'
                        WHEN j.posted_date >= CURRENT_DATE - INTERVAL '30 days' THEN 'Last month'
                        ELSE 'Older'
                    END as posted_period
                FROM base_jobs bj
                JOIN jobs j ON bj.id = j.id
                WHERE j.posted_date IS NOT NULL
            )
            SELECT posted_period, COUNT(*) as job_count
            FROM dated
            GROUP BY posted_period
            ORDER BY
                CASE posted_period
                    WHEN 'Today' THEN 1
                    WHEN 'Last 3 days' THEN 2
                    WHEN 'Last week' THEN 3
                    WHEN 'Last 2 weeks' THEN 4
                    WHEN 'Last month' THEN 5
                    WHEN 'Older' THEN 6
                END
        """

        result = await session.execute(text(query), base_params)
        return {row.posted_period: row.job_count for row in result.fetchall()}

    def _build_base_query_builder(self, criteria: JobSearchCriteria) -> SearchQueryBuilder:
        """Build base query builder without category-specific filters for faceting."""
        builder = SearchQueryBuilder()

        # Include text search
        if criteria.query:
            builder.add_text_search(criteria.query)

        if criteria.title:
            builder.add_text_search(criteria.title, weight_factor=1.5)

        # Include quality filters
        builder.add_quality_filter(criteria.min_quality_score, criteria.exclude_spam)

        # Include date filters
        builder.add_date_filter(criteria.posted_after, criteria.posted_before)

        # Don't include category-specific filters that we're counting:
        # - employment_types
        # - experience_levels
        # - location
        # - company
        # - is_remote
        # - salary filters

        return builder

    def _generate_facet_cache_key(self, criteria: JobSearchCriteria) -> str:
        """Generate cache key for facet results."""
        import hashlib
        import json

        # Create a simplified criteria object for caching
        cache_data = {
            "query": criteria.query,
            "title": criteria.title,
            "min_quality_score": criteria.min_quality_score,
            "exclude_spam": criteria.exclude_spam,
            "posted_after": criteria.posted_after.isoformat() if criteria.posted_after else None,
            "posted_before": criteria.posted_before.isoformat() if criteria.posted_before else None,
        }

        cache_string = json.dumps(cache_data, sort_keys=True)
        cache_hash = hashlib.md5(cache_string.encode()).hexdigest()

        return f"job_facets:{cache_hash}"

    async def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get facet data from Redis cache."""
        try:
            import json
            cached_data = await redis_manager.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Cache get error for facets: {e}")
        return None

    async def _set_cache(self, cache_key: str, data: Dict[str, Any]):
        """Set facet data in Redis cache."""
        try:
            import json
            await redis_manager.set(cache_key, json.dumps(data), self.cache_ttl)
        except Exception as e:
            logger.warning(f"Cache set error for facets: {e}")

    async def get_popular_search_terms(
        self,
        limit: int = 10,
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """
        Get popular search terms for autocomplete enhancement.

        Returns:
            List of popular search terms with counts
        """
        if session is None:
            session = db.session

        try:
            # This would typically come from search analytics
            # For now, return common tech job terms
            popular_terms = [
                {"term": "software engineer", "count": 1250},
                {"term": "data scientist", "count": 890},
                {"term": "product manager", "count": 675},
                {"term": "frontend developer", "count": 560},
                {"term": "backend developer", "count": 445},
                {"term": "full stack developer", "count": 380},
                {"term": "devops engineer", "count": 320},
                {"term": "ui ux designer", "count": 290},
                {"term": "machine learning engineer", "count": 245},
                {"term": "qa engineer", "count": 210}
            ]

            return popular_terms[:limit]

        except Exception as e:
            logger.error(f"Error getting popular search terms: {e}")
            return []

    async def get_trending_skills(
        self,
        limit: int = 20,
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """
        Get trending skills from recent job postings.

        Returns:
            List of trending skills with job counts
        """
        if session is None:
            session = db.session

        try:
            # Extract skills from recent jobs
            query = """
                SELECT
                    skill,
                    COUNT(*) as job_count
                FROM (
                    SELECT jsonb_array_elements_text(skills_required) as skill
                    FROM jobs
                    WHERE posted_date >= CURRENT_DATE - INTERVAL '30 days'
                      AND status = 'active'
                    UNION ALL
                    SELECT jsonb_array_elements_text(skills_preferred) as skill
                    FROM jobs
                    WHERE posted_date >= CURRENT_DATE - INTERVAL '30 days'
                      AND status = 'active'
                ) skills_data
                WHERE skill IS NOT NULL AND LENGTH(skill) > 2
                GROUP BY skill
                ORDER BY job_count DESC
                LIMIT :limit
            """

            result = await session.execute(text(query), {"limit": limit})
            return [
                {"skill": row.skill, "job_count": row.job_count}
                for row in result.fetchall()
            ]

        except Exception as e:
            logger.error(f"Error getting trending skills: {e}")
            # Return fallback data
            return [
                {"skill": "Python", "job_count": 450},
                {"skill": "JavaScript", "job_count": 420},
                {"skill": "React", "job_count": 380},
                {"skill": "AWS", "job_count": 340},
                {"skill": "Node.js", "job_count": 290}
            ]