"""Job search API endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request
from fastapi.responses import JSONResponse

from ...decorators.api_decorators import log_api_call, standardize_response
from ...core.responses import APIResponse
from .service import JobAPIService
from .schema import (
    JobSearchRequest, JobSearchResponse, JobDetailResponse,
    AutocompleteRequest, AutocompleteResponse, PopularJobsResponse,
    RecentJobsResponse, RecommendedJobsResponse, JobAnalyticsRequest
)
from .facets import router as facets_router

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


# Initialize service
job_service = JobAPIService()


# Import authentication dependencies
from ...decorators.auth_decorators import get_current_user_optional as auth_get_current_user_optional, get_current_user
from ...models import UserDB


@router.get("/search")
@log_api_call(log_request=True)
@standardize_response(success_message="Jobs retrieved successfully")
async def search_jobs(
    # Text search parameters
    q: Optional[str] = Query(None, description="Search query", max_length=200),
    title: Optional[str] = Query(None, description="Job title filter", max_length=200),
    company: Optional[str] = Query(None, description="Company name filter", max_length=200),
    location: Optional[str] = Query(None, description="Location filter", max_length=200),

    # Job characteristics
    employment_types: Optional[str] = Query(None, description="Employment types (comma-separated)"),
    experience_levels: Optional[str] = Query(None, description="Experience levels (comma-separated)"),
    remote: Optional[bool] = Query(None, description="Remote work filter"),

    # Salary filters
    min_salary: Optional[int] = Query(None, ge=0, description="Minimum salary"),
    max_salary: Optional[int] = Query(None, ge=0, description="Maximum salary"),
    salary_currency: Optional[str] = Query("USD", description="Salary currency"),
    salary_disclosed: Optional[bool] = Query(None, description="Only jobs with disclosed salary"),

    # Skills
    required_skills: Optional[str] = Query(None, description="Required skills (comma-separated)"),
    preferred_skills: Optional[str] = Query(None, description="Preferred skills (comma-separated)"),

    # Date filters
    posted_within: Optional[int] = Query(None, ge=1, le=365, description="Posted within N days"),

    # Quality filters
    min_quality_score: Optional[float] = Query(None, ge=0, le=100, description="Minimum quality score"),
    exclude_spam: bool = Query(True, description="Exclude suspected spam"),

    # Pagination and sorting
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    sort_by: str = Query("relevance", description="Sort field (relevance, posted_date, salary)"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),

    # User context
    current_user_obj: Optional[UserDB] = Depends(auth_get_current_user_optional)
) -> JobSearchResponse:
    """
    Advanced job search with multiple filters.

    Supports text search, location filtering, salary ranges, skills matching,
    and various other filters. Results are paginated and can be sorted by
    relevance, date, or salary.
    """
    try:
        # Parse list parameters
        from ...models.common import EmploymentType, ExperienceLevel, Currency

        parsed_employment_types = None
        if employment_types:
            try:
                parsed_employment_types = [
                    EmploymentType(t.strip()) for t in employment_types.split(",") if t.strip()
                ]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid employment type")

        parsed_experience_levels = None
        if experience_levels:
            try:
                parsed_experience_levels = [
                    ExperienceLevel(l.strip()) for l in experience_levels.split(",") if l.strip()
                ]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid experience level")

        parsed_currency = Currency.USD
        if salary_currency:
            try:
                parsed_currency = Currency(salary_currency.upper())
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid currency")

        parsed_required_skills = None
        if required_skills:
            parsed_required_skills = [s.strip() for s in required_skills.split(",") if s.strip()]

        parsed_preferred_skills = None
        if preferred_skills:
            parsed_preferred_skills = [s.strip() for s in preferred_skills.split(",") if s.strip()]

        # Create search request
        search_request = JobSearchRequest(
            q=q,
            title=title,
            company=company,
            location=location,
            employment_types=parsed_employment_types,
            experience_levels=parsed_experience_levels,
            is_remote=remote,
            min_salary=min_salary,
            max_salary=max_salary,
            salary_currency=parsed_currency,
            salary_disclosed_only=salary_disclosed,
            required_skills=parsed_required_skills,
            preferred_skills=parsed_preferred_skills,
            posted_within_days=posted_within,
            min_quality_score=min_quality_score,
            exclude_spam=exclude_spam,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order
        )

        # Perform search
        current_user = current_user_obj.id if current_user_obj else None
        response = await job_service.search_jobs(search_request, current_user)
        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/search/enhanced")
@log_api_call(log_request=True)
@standardize_response(success_message="Enhanced search completed successfully")
async def search_jobs_enhanced(
    # Text search parameters
    q: Optional[str] = Query(None, description="Search query", max_length=200),
    title: Optional[str] = Query(None, description="Job title filter", max_length=200),
    company: Optional[str] = Query(None, description="Company name filter", max_length=200),
    location: Optional[str] = Query(None, description="Location filter", max_length=200),

    # Job characteristics
    employment_types: Optional[str] = Query(None, description="Employment types (comma-separated)"),
    experience_levels: Optional[str] = Query(None, description="Experience levels (comma-separated)"),
    remote: Optional[bool] = Query(None, description="Remote work filter"),

    # Salary filters
    min_salary: Optional[int] = Query(None, ge=0, description="Minimum salary"),
    max_salary: Optional[int] = Query(None, ge=0, description="Maximum salary"),
    salary_currency: Optional[str] = Query("USD", description="Salary currency"),
    salary_disclosed: Optional[bool] = Query(None, description="Only jobs with disclosed salary"),

    # Skills
    required_skills: Optional[str] = Query(None, description="Required skills (comma-separated)"),
    preferred_skills: Optional[str] = Query(None, description="Preferred skills (comma-separated)"),

    # Date filters
    posted_within: Optional[int] = Query(None, ge=1, le=365, description="Posted within N days"),

    # Quality filters
    min_quality_score: Optional[float] = Query(None, ge=0, le=100, description="Minimum quality score"),
    exclude_spam: bool = Query(True, description="Exclude suspected spam"),

    # Enhanced features
    include_facets: bool = Query(False, description="Include faceted search results"),

    # Pagination and sorting
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    sort_by: str = Query("relevance", description="Sort field (relevance, posted_date, salary)"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),

    # User context
    current_user_obj: Optional[UserDB] = Depends(auth_get_current_user_optional)
) -> dict:
    """
    Enhanced job search with full-text search, relevance scoring, and optional facets.

    This endpoint provides superior search performance and accuracy compared to the basic
    search endpoint by utilizing PostgreSQL full-text search with proper relevance scoring.

    Features:
    - PostgreSQL tsvector full-text search for better accuracy
    - Advanced relevance scoring combining text match, quality, and freshness
    - Optional faceted search results showing filter counts
    - Database-driven autocomplete suggestions
    - Enhanced caching strategy
    - Better performance for large datasets

    Set `include_facets=true` to get aggregated counts for all filter categories.
    """
    try:
        # Parse list parameters (same as basic search)
        from ...models.common import EmploymentType, ExperienceLevel, Currency
        from ...services.enhanced_job_search_service import EnhancedJobSearchService

        parsed_employment_types = None
        if employment_types:
            try:
                parsed_employment_types = [
                    EmploymentType(t.strip()) for t in employment_types.split(",") if t.strip()
                ]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid employment type")

        parsed_experience_levels = None
        if experience_levels:
            try:
                parsed_experience_levels = [
                    ExperienceLevel(l.strip()) for l in experience_levels.split(",") if l.strip()
                ]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid experience level")

        parsed_currency = Currency.USD
        if salary_currency:
            try:
                parsed_currency = Currency(salary_currency.upper())
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid currency")

        parsed_required_skills = None
        if required_skills:
            parsed_required_skills = [s.strip() for s in required_skills.split(",") if s.strip()]

        parsed_preferred_skills = None
        if preferred_skills:
            parsed_preferred_skills = [s.strip() for s in preferred_skills.split(",") if s.strip()]

        # Create search request
        search_request = JobSearchRequest(
            q=q,
            title=title,
            company=company,
            location=location,
            employment_types=parsed_employment_types,
            experience_levels=parsed_experience_levels,
            is_remote=remote,
            min_salary=min_salary,
            max_salary=max_salary,
            salary_currency=parsed_currency,
            salary_disclosed_only=salary_disclosed,
            required_skills=parsed_required_skills,
            preferred_skills=parsed_preferred_skills,
            posted_within_days=posted_within,
            min_quality_score=min_quality_score,
            exclude_spam=exclude_spam,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order
        )

        # Use enhanced search service directly
        enhanced_service = EnhancedJobSearchService()
        criteria = job_service._convert_to_search_criteria(search_request)

        # Perform enhanced search with optional facets
        current_user = current_user_obj.id if current_user_obj else None
        search_result = await enhanced_service.search_jobs(
            criteria,
            current_user,
            include_facets=include_facets
        )

        # Convert to API response format
        api_response = job_service._convert_to_api_response(search_result)

        # Add facets to response if included
        if include_facets and "facets" in search_result:
            api_response.metadata.facets = search_result["facets"]
            api_response.metadata.facet_time_ms = search_result.get("facet_time_ms", 0)

        return api_response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Enhanced search failed: {str(e)}")


@router.get("/popular")
@log_api_call(log_request=True)
@standardize_response(success_message="Popular jobs retrieved successfully")
async def get_popular_jobs(
    limit: int = Query(10, ge=1, le=50, description="Number of jobs to return")
) -> PopularJobsResponse:
    """
    Get trending/popular jobs.

    Returns jobs with high view counts and engagement from the last 30 days,
    filtered for quality and relevance.
    """
    try:
        response = await job_service.get_popular_jobs(limit)
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get popular jobs: {str(e)}")


@router.get("/recent")
@log_api_call(log_request=True)
@standardize_response(success_message="Recent jobs retrieved successfully")
async def get_recent_jobs(
    limit: int = Query(20, ge=1, le=100, description="Number of jobs to return")
) -> RecentJobsResponse:
    """
    Get recently posted jobs.

    Returns the most recently posted jobs from the last 7 days,
    sorted by posting date in descending order.
    """
    try:
        response = await job_service.get_recent_jobs(limit)
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get recent jobs: {str(e)}")


@router.get("/recommended")
@log_api_call(log_request=True)
@standardize_response(success_message="Recommended jobs retrieved successfully")
async def get_recommended_jobs(
    limit: int = Query(20, ge=1, le=100, description="Number of jobs to return"),
    current_user_obj: UserDB = Depends(get_current_user)
) -> RecommendedJobsResponse:
    """
    Get personalized job recommendations.

    Returns job recommendations based on user profile, search history,
    and preferences. Requires authentication.
    """
    try:
        current_user = current_user_obj.id
        response = await job_service.get_recommended_jobs(current_user, limit)
        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get recommended jobs: {str(e)}")


@router.get("/autocomplete")
@log_api_call(log_request=True)
@standardize_response(success_message="Suggestions retrieved successfully")
async def get_autocomplete_suggestions(
    q: str = Query(..., min_length=1, max_length=100, description="Search query"),
    type: str = Query("all", pattern="^(all|title|company|location|skills)$", description="Suggestion type"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of suggestions")
) -> AutocompleteResponse:
    """
    Get autocomplete suggestions for search queries.

    Provides intelligent suggestions for job titles, company names,
    locations, and skills based on the query string.
    """
    try:
        request = AutocompleteRequest(q=q, type=type, limit=limit)
        response = await job_service.get_autocomplete_suggestions(request)
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get suggestions: {str(e)}")


# Health check endpoint for job service
@router.get("/health")
@log_api_call()
@standardize_response(success_message="Job service is healthy")
async def job_service_health():
    """
    Health check endpoint for job search service.

    Returns the status of job search functionality including
    database connectivity and cache availability.
    """
    try:
        # Basic health check
        from sqlalchemy import text
        from ...core.database import db
        from ...core.redis import redis_manager

        # Check database connection
        async with db.session as session:
            await session.execute(text("SELECT 1"))

        # Check Redis connection
        await redis_manager.ping()

        return {
            "status": "healthy",
            "database": "connected",
            "cache": "connected",
            "service": "job_search",
            "timestamp": "2025-01-15T12:00:00Z"
        }

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


# Include facets router
router.include_router(facets_router)


# Path-parameter routes registered last so literal paths above
# (/search, /popular, /recent, /recommended, /autocomplete, /health, /facets/*)
# are matched before falling through to /{job_id}.
@router.get("/{job_id}")
@log_api_call(log_request=True)
@standardize_response(success_message="Job details retrieved successfully")
async def get_job_details(
    job_id: int = Path(..., description="Job ID"),
    current_user_obj: Optional[UserDB] = Depends(auth_get_current_user_optional)
) -> JobDetailResponse:
    """
    Get detailed information for a specific job.

    Returns comprehensive job details including description, requirements,
    company information, and application details. Tracks view analytics.
    """
    try:
        current_user = current_user_obj.id if current_user_obj else None
        response = await job_service.get_job_details(job_id, current_user)

        if not response:
            raise HTTPException(status_code=404, detail="Job not found")

        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get job details: {str(e)}")


@router.post("/{job_id}/analytics")
@log_api_call(log_request=True)
@standardize_response(success_message="Analytics tracked successfully")
async def track_job_analytics(
    job_id: int = Path(..., description="Job ID"),
    request: JobAnalyticsRequest = ...,
    current_user_obj: Optional[UserDB] = Depends(auth_get_current_user_optional)
):
    """
    Track job analytics (views, clicks, applications).

    Records user interactions with jobs for analytics and recommendation
    improvements. Supports view, click, and apply tracking.
    """
    try:
        current_user = current_user_obj.id if current_user_obj else None
        result = await job_service.track_job_analytics(job_id, request, current_user)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to track analytics: {str(e)}")