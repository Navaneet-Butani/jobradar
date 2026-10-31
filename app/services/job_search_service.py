"""Job search service for business logic and search operations."""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import db
from ..core.redis import redis_manager
from ..repositories.job_repository import JobRepository
from ..models import JobDB
from ..models.job import JobSearchCriteria
from ..models.common import JobStatus

logger = logging.getLogger(__name__)


class JobSearchService:
    """Service for job search operations with caching and analytics."""

    def __init__(self):
        self.job_repo = JobRepository()
        self.cache_prefix = "job_search"
        self.cache_ttl = 300  # 5 minutes

    async def search_jobs(
        self,
        criteria: JobSearchCriteria,
        user_id: Optional[int] = None,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Main job search method with caching and analytics.

        Args:
            criteria: Search criteria and filters
            user_id: Optional user ID for personalization
            session: Optional database session

        Returns:
            Dict with jobs, total count, and metadata
        """
        try:
            # Generate cache key based on search criteria
            cache_key = self._generate_cache_key(criteria, user_id)

            # Try to get from cache first
            cached_result = await self._get_from_cache(cache_key)
            if cached_result:
                logger.info(f"Cache hit for search: {criteria.query}")
                return cached_result

            # Track search analytics
            await self._track_search_query(criteria, user_id)

            # Perform database search
            start_time = datetime.utcnow()
            jobs, total_count = await self.job_repo.search_jobs(criteria, session)
            search_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Enhance results with additional data
            enhanced_jobs = await self._enhance_job_results(jobs, user_id, session)

            # Calculate relevance scores
            scored_jobs = await self._apply_relevance_scoring(enhanced_jobs, criteria)

            # Build response
            result = {
                "jobs": scored_jobs,
                "total": total_count,
                "page": (criteria.offset // criteria.limit) + 1,
                "limit": criteria.limit,
                "pages": (total_count + criteria.limit - 1) // criteria.limit,
                "query_time_ms": search_time_ms,
                "filters_applied": self._get_applied_filters(criteria),
                "has_next": (criteria.offset + criteria.limit) < total_count,
                "has_previous": criteria.offset > 0
            }

            # Cache the result
            await self._set_cache(cache_key, result, self.cache_ttl)

            logger.info(f"Search completed: {len(jobs)} jobs found in {search_time_ms}ms")
            return result

        except Exception as e:
            logger.error(f"Error in job search: {e}")
            raise

    async def get_job_details(
        self,
        job_id: int,
        user_id: Optional[int] = None,
        session: Optional[AsyncSession] = None
    ) -> Optional[Dict[str, Any]]:
        """Get detailed job information with view tracking."""
        try:
            # Get job from repository
            job = await self.job_repo.get_by_id(job_id, session)
            if not job:
                return None

            # Track job view
            await self._track_job_view(job_id, user_id)

            # Enhance with additional data
            enhanced_job = await self._enhance_single_job(job, user_id, session)

            return enhanced_job

        except Exception as e:
            logger.error(f"Error getting job details for {job_id}: {e}")
            raise

    async def get_popular_jobs(
        self,
        limit: int = 10,
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """Get trending/popular jobs with caching."""
        try:
            cache_key = f"{self.cache_prefix}:popular:{limit}"

            # Check cache first
            cached_result = await self._get_from_cache(cache_key)
            if cached_result:
                return cached_result

            # Create criteria for popular jobs (high view count, recent)
            criteria = JobSearchCriteria(
                limit=limit,
                offset=0,
                sort_by="views_count",
                sort_order="desc",
                posted_after=datetime.utcnow() - timedelta(days=30),
                min_quality_score=50.0
            )

            jobs, _ = await self.job_repo.search_jobs(criteria, session)
            enhanced_jobs = await self._enhance_job_results(jobs, None, session)

            # Cache for 10 minutes
            await self._set_cache(cache_key, enhanced_jobs, 600)

            return enhanced_jobs

        except Exception as e:
            logger.error(f"Error getting popular jobs: {e}")
            raise

    async def get_recent_jobs(
        self,
        limit: int = 20,
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """Get recently posted jobs."""
        try:
            criteria = JobSearchCriteria(
                limit=limit,
                offset=0,
                sort_by="posted_date",
                sort_order="desc",
                posted_after=datetime.utcnow() - timedelta(days=7)
            )

            jobs, _ = await self.job_repo.search_jobs(criteria, session)
            enhanced_jobs = await self._enhance_job_results(jobs, None, session)

            return enhanced_jobs

        except Exception as e:
            logger.error(f"Error getting recent jobs: {e}")
            raise

    async def get_autocomplete_suggestions(
        self,
        query: str,
        suggestion_type: str = "all",
        limit: int = 10
    ) -> List[str]:
        """Get search suggestions based on query."""
        try:
            cache_key = f"{self.cache_prefix}:autocomplete:{suggestion_type}:{query.lower()}"

            # Check cache first
            cached_result = await self._get_from_cache(cache_key)
            if cached_result:
                return cached_result

            suggestions = []

            if suggestion_type in ["all", "title"]:
                # Get title suggestions
                title_suggestions = await self._get_title_suggestions(query, limit // 2)
                suggestions.extend(title_suggestions)

            if suggestion_type in ["all", "company"]:
                # Get company suggestions
                company_suggestions = await self._get_company_suggestions(query, limit // 2)
                suggestions.extend(company_suggestions)

            if suggestion_type in ["all", "location"]:
                # Get location suggestions
                location_suggestions = await self._get_location_suggestions(query, limit // 2)
                suggestions.extend(location_suggestions)

            # Remove duplicates and limit results
            unique_suggestions = list(dict.fromkeys(suggestions))[:limit]

            # Cache for 1 hour
            await self._set_cache(cache_key, unique_suggestions, 3600)

            return unique_suggestions

        except Exception as e:
            logger.error(f"Error getting autocomplete suggestions: {e}")
            return []

    async def get_recommended_jobs(
        self,
        user_id: int,
        limit: int = 20,
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """Get personalized job recommendations (basic implementation)."""
        try:
            # Basic recommendation: recent jobs matching user's previous searches
            # This would be enhanced with ML algorithms in the future

            criteria = JobSearchCriteria(
                limit=limit,
                offset=0,
                sort_by="posted_date",
                sort_order="desc",
                posted_after=datetime.utcnow() - timedelta(days=14),
                min_quality_score=60.0
            )

            jobs, _ = await self.job_repo.search_jobs(criteria, session)
            enhanced_jobs = await self._enhance_job_results(jobs, user_id, session)

            return enhanced_jobs

        except Exception as e:
            logger.error(f"Error getting recommended jobs for user {user_id}: {e}")
            raise

    # Private methods

    def _generate_cache_key(self, criteria: JobSearchCriteria, user_id: Optional[int]) -> str:
        """Generate cache key from search criteria."""
        key_data = {
            "query": criteria.query,
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
            "user_id": user_id
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

    async def _enhance_job_results(
        self,
        jobs: List[JobDB],
        user_id: Optional[int],
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """Enhance job results with additional data."""
        enhanced_jobs = []

        for job in jobs:
            enhanced_job = await self._enhance_single_job(job, user_id, session)
            enhanced_jobs.append(enhanced_job)

        return enhanced_jobs

    async def _enhance_single_job(
        self,
        job: JobDB,
        user_id: Optional[int],
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Enhance a single job with additional data."""
        job_data = {
            "id": job.id,
            "uuid": str(job.uuid),
            "title": job.title,
            "company": {
                "id": job.company.id if job.company else None,
                "name": job.company.name if job.company else "Unknown",
                "logo_url": job.company.logo_url if job.company else None,
                "website": job.company.website if job.company else None
            },
            "location": {
                "raw": job.location_raw,
                "city": job.city,
                "country": job.country,
                "is_remote": job.is_remote
            },
            "employment_type": job.employment_type.name if job.employment_type else None,
            "experience_level": job.experience_level.name if job.experience_level else None,
            "salary": {
                "min": float(job.salary_min) if job.salary_min else None,
                "max": float(job.salary_max) if job.salary_max else None,
                "currency": job.salary_currency,
                "disclosed": job.salary_disclosed
            },
            "posted_date": job.posted_date.isoformat() if job.posted_date else None,
            "apply_url": job.apply_url,
            "skills_required": [s["name"] if isinstance(s, dict) else s for s in (job.skills_required or [])],
            "skills_preferred": [s["name"] if isinstance(s, dict) else s for s in (job.skills_preferred or [])],
            "quality_score": float(job.quality_score),
            "views_count": job.views_count,
            "is_saved": False  # TODO: Check if user saved this job
        }

        return job_data

    async def _apply_relevance_scoring(
        self,
        jobs: List[Dict[str, Any]],
        criteria: JobSearchCriteria
    ) -> List[Dict[str, Any]]:
        """Apply relevance scoring to job results."""
        for job in jobs:
            relevance_score = self._calculate_relevance_score(job, criteria)
            job["relevance_score"] = relevance_score

        return jobs

    def _calculate_relevance_score(self, job: Dict[str, Any], criteria: JobSearchCriteria) -> float:
        """Calculate relevance score for a job."""
        score = 0.0

        # Base quality score (0-40 points)
        score += (job["quality_score"] / 100) * 40

        # Freshness score (0-30 points)
        if job["posted_date"]:
            posted_date = datetime.fromisoformat(job["posted_date"].replace('Z', '+00:00'))
            days_old = (datetime.utcnow() - posted_date.replace(tzinfo=None)).days

            if days_old <= 1:
                score += 30
            elif days_old <= 3:
                score += 25
            elif days_old <= 7:
                score += 20
            elif days_old <= 14:
                score += 15
            elif days_old <= 30:
                score += 10

        # Salary disclosed bonus (0-10 points)
        if job["salary"]["disclosed"]:
            score += 10

        # Text match bonus (0-20 points)
        if criteria.query:
            query_lower = criteria.query.lower()
            title_lower = job["title"].lower()

            if query_lower in title_lower:
                score += 20
            elif any(word in title_lower for word in query_lower.split()):
                score += 10

        return min(score, 100.0)

    def _get_applied_filters(self, criteria: JobSearchCriteria) -> List[str]:
        """Get list of applied filters for response metadata."""
        filters = []

        if criteria.query:
            filters.append("text_search")
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
                "filters": self._get_applied_filters(criteria)
            }

            # Store in Redis for analytics processing
            analytics_key = f"analytics:search:{datetime.utcnow().strftime('%Y-%m-%d')}"
            await redis_manager.lpush(analytics_key, json.dumps(analytics_data))

        except Exception as e:
            logger.warning(f"Error tracking search query: {e}")

    async def _track_job_view(self, job_id: int, user_id: Optional[int]):
        """Track job view for analytics."""
        try:
            # Increment view count in database (async)
            await self.job_repo.increment_view_count(job_id)

            # Track in analytics
            analytics_data = {
                "job_id": job_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "action": "view"
            }

            analytics_key = f"analytics:job_views:{datetime.utcnow().strftime('%Y-%m-%d')}"
            await redis_manager.lpush(analytics_key, json.dumps(analytics_data))

        except Exception as e:
            logger.warning(f"Error tracking job view: {e}")

    async def _get_title_suggestions(self, query: str, limit: int) -> List[str]:
        """Get job title suggestions."""
        # This would query the database for similar titles
        # For now, return some common tech job titles that match the query
        common_titles = [
            "Software Engineer", "Senior Software Engineer", "Frontend Developer",
            "Backend Developer", "Full Stack Developer", "Data Scientist",
            "Product Manager", "DevOps Engineer", "UI/UX Designer", "QA Engineer",
            "Tech Lead", "Engineering Manager", "Data Engineer", "Machine Learning Engineer"
        ]

        query_lower = query.lower()
        matching_titles = [
            title for title in common_titles
            if query_lower in title.lower()
        ]

        return matching_titles[:limit]

    async def _get_company_suggestions(self, query: str, limit: int) -> List[str]:
        """Get company name suggestions."""
        # This would query the companies table
        # For now, return some common tech companies
        common_companies = [
            "Google", "Apple", "Microsoft", "Amazon", "Meta", "Netflix",
            "Tesla", "Uber", "Airbnb", "Spotify", "Stripe", "Slack"
        ]

        query_lower = query.lower()
        matching_companies = [
            company for company in common_companies
            if query_lower in company.lower()
        ]

        return matching_companies[:limit]

    async def _get_location_suggestions(self, query: str, limit: int) -> List[str]:
        """Get location suggestions."""
        common_locations = [
            "San Francisco, CA", "New York, NY", "Seattle, WA", "Austin, TX",
            "Boston, MA", "Los Angeles, CA", "Chicago, IL", "Denver, CO",
            "Remote", "London, UK", "Berlin, Germany", "Toronto, Canada"
        ]

        query_lower = query.lower()
        matching_locations = [
            location for location in common_locations
            if query_lower in location.lower()
        ]

        return matching_locations[:limit]