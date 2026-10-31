"""Job API service layer for handling business logic."""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import db
from ...services.job_search_service import JobSearchService
from ...services.enhanced_job_search_service import EnhancedJobSearchService
from ...models.job import JobSearchCriteria
from ...models.common import EmploymentType, ExperienceLevel, Currency
from .schema import (
    JobSearchRequest, JobSearchResponse, JobDetailResponse, AutocompleteRequest,
    AutocompleteResponse, PopularJobsResponse, RecentJobsResponse,
    RecommendedJobsResponse, JobAnalyticsRequest, JobSummary, JobDetail,
    SearchMetadata
)

logger = logging.getLogger(__name__)

# Below this, a stored "description" is a stub rather than a job description —
# a source's boilerplate footer, or a leftover placeholder. Matches the
# threshold the description backfill selects on.
MIN_USEFUL_DESCRIPTION_CHARS = 50


class JobAPIService:
    """Service class for job API operations."""

    def __init__(self):
        self.job_search_service = JobSearchService()
        self.enhanced_search_service = EnhancedJobSearchService()

    async def search_jobs(
        self,
        request: JobSearchRequest,
        user_id: Optional[int] = None
    ) -> JobSearchResponse:
        """
        Handle job search request.

        Args:
            request: Job search request parameters
            user_id: Optional authenticated user ID

        Returns:
            JobSearchResponse with search results
        """
        try:
            # Convert API request to search criteria
            criteria = self._convert_to_search_criteria(request)

            # Use enhanced search service for better performance and relevance
            search_result = await self.enhanced_search_service.search_jobs(
                criteria,
                user_id,
                include_facets=False  # Can be made configurable via request parameter
            )

            # Convert service response to API response format
            api_response = self._convert_to_api_response(search_result)

            logger.info(f"Enhanced job search completed: {len(api_response.data)} results")
            return api_response

        except Exception as e:
            logger.error(f"Error in enhanced job search API: {e}")
            raise

    async def get_job_details(
        self,
        job_id: int,
        user_id: Optional[int] = None
    ) -> Optional[JobDetailResponse]:
        """
        Get detailed job information.

        Args:
            job_id: Job ID to retrieve
            user_id: Optional authenticated user ID

        Returns:
            JobDetailResponse with job details or None if not found
        """
        try:
            # Use enhanced search service for job details
            job_data = await self.enhanced_search_service.get_job_details(job_id, user_id)

            if not job_data:
                return None

            # Hirist's search feed carries no description, so most of its rows
            # land empty. Fetch the real one the first time somebody opens the
            # job and store it — every later view is free. Failure is silent by
            # design: a missing description must not fail the page.
            if len((job_data.get("description") or "").strip()) < MIN_USEFUL_DESCRIPTION_CHARS:
                job_data["description"] = (
                    await self._fetch_missing_description(job_id) or job_data.get("description")
                )

            # Convert to detail response format
            job_detail = self._convert_to_job_detail(job_data)

            return JobDetailResponse(
                status=True,
                data=job_detail,
                message="Job details retrieved successfully"
            )

        except Exception as e:
            logger.error(f"Error getting enhanced job details for {job_id}: {e}")
            raise

    async def get_popular_jobs(
        self,
        limit: int = 10
    ) -> PopularJobsResponse:
        """Get popular/trending jobs."""
        try:
            jobs_data = await self.job_search_service.get_popular_jobs(limit)

            jobs = [self._convert_to_job_summary(job) for job in jobs_data]

            return PopularJobsResponse(
                status=True,
                data=jobs,
                message="Popular jobs retrieved successfully"
            )

        except Exception as e:
            logger.error(f"Error getting popular jobs: {e}")
            raise

    async def get_recent_jobs(
        self,
        limit: int = 20
    ) -> RecentJobsResponse:
        """Get recently posted jobs."""
        try:
            jobs_data = await self.job_search_service.get_recent_jobs(limit)

            jobs = [self._convert_to_job_summary(job) for job in jobs_data]

            return RecentJobsResponse(
                status=True,
                data=jobs,
                message="Recent jobs retrieved successfully"
            )

        except Exception as e:
            logger.error(f"Error getting recent jobs: {e}")
            raise

    async def get_recommended_jobs(
        self,
        user_id: int,
        limit: int = 20
    ) -> RecommendedJobsResponse:
        """Get personalized job recommendations."""
        try:
            jobs_data = await self.job_search_service.get_recommended_jobs(user_id, limit)

            jobs = [self._convert_to_job_summary(job) for job in jobs_data]

            return RecommendedJobsResponse(
                status=True,
                data=jobs,
                message="Recommended jobs retrieved successfully"
            )

        except Exception as e:
            logger.error(f"Error getting recommended jobs for user {user_id}: {e}")
            raise

    async def get_autocomplete_suggestions(
        self,
        request: AutocompleteRequest
    ) -> AutocompleteResponse:
        """Get autocomplete suggestions."""
        try:
            # Use enhanced search service for better autocomplete
            suggestions = await self.enhanced_search_service.get_autocomplete_suggestions(
                request.q, request.type, request.limit
            )

            return AutocompleteResponse(
                status=True,
                data=suggestions,
                message="Enhanced suggestions retrieved successfully"
            )

        except Exception as e:
            logger.error(f"Error getting enhanced autocomplete suggestions: {e}")
            raise

    async def track_job_analytics(
        self,
        job_id: int,
        request: JobAnalyticsRequest,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Track job analytics (views, clicks, applications)."""
        try:
            if request.action == "view":
                await self.job_search_service._track_job_view(job_id, user_id)
            elif request.action == "click":
                # Track click analytics
                await self._track_job_click(job_id, user_id, request)
            elif request.action == "apply":
                # Track application analytics
                await self._track_job_application(job_id, user_id, request)

            return {
                "status": True,
                "message": f"Analytics tracked for action: {request.action}"
            }

        except Exception as e:
            logger.error(f"Error tracking job analytics: {e}")
            raise

    # Private helper methods

    def _convert_to_search_criteria(self, request: JobSearchRequest) -> JobSearchCriteria:
        """Convert API request to search criteria."""
        # Handle date filter
        posted_after = None
        if request.posted_within_days:
            posted_after = datetime.utcnow() - timedelta(days=request.posted_within_days)

        # Calculate offset from page
        offset = (request.page - 1) * request.limit

        return JobSearchCriteria(
            query=request.q,
            title=request.title,
            company=request.company,
            location=request.location,
            employment_types=request.employment_types,
            experience_levels=request.experience_levels,
            is_remote=request.is_remote,
            min_salary=request.min_salary,
            max_salary=request.max_salary,
            salary_currency=request.salary_currency,
            salary_disclosed_only=request.salary_disclosed_only,
            required_skills=request.required_skills,
            preferred_skills=request.preferred_skills,
            posted_after=posted_after,
            min_quality_score=request.min_quality_score,
            exclude_spam=request.exclude_spam,
            limit=request.limit,
            offset=offset,
            sort_by=request.sort_by,
            sort_order=request.sort_order
        )

    def _convert_to_api_response(self, search_result: Dict[str, Any]) -> JobSearchResponse:
        """Convert service response to API response format."""
        # Convert job data to JobSummary objects
        jobs = [self._convert_to_job_summary(job) for job in search_result["jobs"]]

        # Create metadata
        metadata = SearchMetadata(
            total=search_result["total"],
            page=search_result["page"],
            limit=search_result["limit"],
            pages=search_result["pages"],
            query_time_ms=search_result["query_time_ms"],
            filters_applied=search_result["filters_applied"],
            has_next=search_result["has_next"],
            has_previous=search_result["has_previous"]
        )

        return JobSearchResponse(
            status=True,
            data=jobs,
            metadata=metadata,
            message="Search completed successfully"
        )

    @staticmethod
    async def _fetch_missing_description(job_id: int) -> Optional[str]:
        """Fetch a description the source's feed omitted, and cache it.

        Only sources with a working detail endpoint are attempted (Hirist
        today); everything else returns None immediately without a request.
        """
        from ...services.enrichment.descriptions import fetch_description_for_job

        try:
            async with db.get_session() as session:
                return await fetch_description_for_job(session, job_id)
        except Exception as e:
            logger.warning(f"On-demand description fetch failed for job {job_id}: {e}")
            return None

    @staticmethod
    def _company_info(company: Dict[str, Any]):
        """Build CompanyInfo from whatever the search layer supplied.

        Everything past name/logo/website is optional: the list query only
        joins `companies` when a company filter is active, so a plain search
        result carries fewer keys than a job detail does.
        """
        from .schema import CompanyInfo

        return CompanyInfo(
            id=company.get("id"),
            name=company.get("name") or "Unknown",
            slug=company.get("slug"),
            logo_url=company.get("logo_url"),
            website=company.get("website"),
            industry=company.get("industry"),
            headquarters=company.get("headquarters"),
            ats_type=company.get("ats_type"),
            tagline=company.get("tagline"),
            description=company.get("description"),
            founded_year=company.get("founded_year"),
            employee_count=company.get("employee_count"),
            employee_range=company.get("employee_range"),
            rating=company.get("rating"),
            rating_count=company.get("rating_count"),
            rating_url=company.get("rating_url"),
            rating_source=company.get("rating_source"),
        )

    def _convert_to_job_summary(self, job_data: Dict[str, Any]) -> JobSummary:
        """Convert job data dict to JobSummary object."""
        from .schema import LocationInfo, SalaryInfo

        return JobSummary(
            id=job_data["id"],
            uuid=job_data["uuid"],
            title=job_data["title"],
            company=self._company_info(job_data["company"]),
            location=LocationInfo(
                raw=job_data["location"]["raw"],
                city=job_data["location"]["city"],
                country=job_data["location"]["country"],
                is_remote=job_data["location"]["is_remote"]
            ),
            employment_type=job_data["employment_type"],
            experience_level=job_data["experience_level"],
            salary=SalaryInfo(
                min=job_data["salary"]["min"],
                max=job_data["salary"]["max"],
                currency=job_data["salary"]["currency"],
                disclosed=job_data["salary"]["disclosed"]
            ),
            posted_date=job_data["posted_date"],
            apply_url=job_data["apply_url"],
            skills_required=job_data["skills_required"],
            skills_preferred=job_data["skills_preferred"],
            quality_score=job_data["quality_score"],
            relevance_score=job_data.get("relevance_score"),
            views_count=job_data["views_count"],
            is_saved=job_data["is_saved"]
        )

    def _convert_to_job_detail(self, job_data: Dict[str, Any]) -> JobDetail:
        """Convert job data dict to JobDetail object."""
        from .schema import LocationInfo, SalaryInfo

        return JobDetail(
            id=job_data["id"],
            uuid=job_data["uuid"],
            title=job_data["title"],
            company=self._company_info(job_data["company"]),
            location=LocationInfo(
                raw=job_data["location"]["raw"],
                city=job_data["location"]["city"],
                country=job_data["location"]["country"],
                is_remote=job_data["location"]["is_remote"]
            ),
            employment_type=job_data["employment_type"],
            experience_level=job_data["experience_level"],
            salary=SalaryInfo(
                min=job_data["salary"]["min"],
                max=job_data["salary"]["max"],
                currency=job_data["salary"]["currency"],
                disclosed=job_data["salary"]["disclosed"]
            ),
            posted_date=job_data["posted_date"],
            apply_url=job_data["apply_url"],
            skills_required=job_data["skills_required"],
            skills_preferred=job_data["skills_preferred"],
            quality_score=job_data["quality_score"],
            relevance_score=job_data.get("relevance_score"),
            views_count=job_data["views_count"],
            is_saved=job_data["is_saved"],
            # Additional detail fields
            description=job_data.get("description"),
            requirements=job_data.get("requirements"),
            responsibilities=job_data.get("responsibilities"),
            benefits=self._parse_benefits(job_data.get("company_benefits")),
            apply_email=job_data.get("apply_email"),
            application_deadline=job_data.get("application_deadline"),
            clicks_count=job_data.get("clicks_count", 0),
            applications_count=job_data.get("applications_count", 0),
            # Provenance
            source_name=job_data.get("source_name"),
            source_url=job_data.get("source_url"),
            first_seen_at=job_data.get("first_seen_at"),
            last_seen_at=job_data.get("last_seen_at"),
            remote_scope=job_data.get("remote_scope"),
            min_exp_years=job_data.get("min_exp_years"),
            max_exp_years=job_data.get("max_exp_years"),
            department=job_data.get("department"),
            work_arrangement=job_data.get("work_arrangement"),
            how_to_apply=job_data.get("how_to_apply"),
            poster_name=job_data.get("poster_name"),
            poster_title=job_data.get("poster_title"),
            source_applicant_count=job_data.get("source_applicant_count"),
            source_view_count=job_data.get("source_view_count"),
        )

    @staticmethod
    def _parse_benefits(raw: Optional[str]) -> List[str]:
        """Split the stored free-text benefits blob into a list, one item per line."""
        if not raw or not raw.strip():
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]

    async def _track_job_click(
        self,
        job_id: int,
        user_id: Optional[int],
        request: JobAnalyticsRequest
    ):
        """Track job click analytics."""
        # This would increment click count and track analytics
        # For now, just log the event
        logger.info(f"Job click tracked: job_id={job_id}, user_id={user_id}")

    async def _track_job_application(
        self,
        job_id: int,
        user_id: Optional[int],
        request: JobAnalyticsRequest
    ):
        """Track job application analytics."""
        # This would increment application count and track analytics
        # For now, just log the event
        logger.info(f"Job application tracked: job_id={job_id}, user_id={user_id}")