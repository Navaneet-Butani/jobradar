"""Faceted search API endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...decorators.api_decorators import log_api_call, standardize_response
from ...core.database import db
from ...services.search.facet_service import FacetService
from ...models.job import JobSearchCriteria
from ...models.common import EmploymentType, ExperienceLevel, Currency
from .schema import JobSearchRequest

router = APIRouter(tags=["job-facets"])

# Initialize facet service
facet_service = FacetService()


@router.post("/facets")
@log_api_call(log_request=True)
@standardize_response(success_message="Facets calculated successfully")
async def get_search_facets(
    # Use the same search parameters as main search
    q: Optional[str] = Query(None, description="Search query", max_length=200),
    title: Optional[str] = Query(None, description="Job title filter", max_length=200),
    location: Optional[str] = Query(None, description="Location filter", max_length=200),
    company: Optional[str] = Query(None, description="Company name filter", max_length=200),

    # Date filters
    posted_within: Optional[int] = Query(None, ge=1, le=365, description="Posted within N days"),

    # Quality filters
    min_quality_score: Optional[float] = Query(None, ge=0, le=100, description="Minimum quality score"),
    exclude_spam: bool = Query(True, description="Exclude suspected spam"),

    # Database session
    db_session: AsyncSession = Depends(lambda: db.session)
) -> dict:
    """
    Get aggregated facet counts for job search filters.

    Returns counts for each filter category based on the current search criteria.
    This helps users understand how many jobs match each filter option.

    Example response:
    ```json
    {
        "status": true,
        "data": {
            "employment_types": {
                "Full-time": 1250,
                "Part-time": 89,
                "Contract": 156
            },
            "experience_levels": {
                "Senior": 890,
                "Mid": 670,
                "Junior": 245
            },
            "locations": {
                "San Francisco, CA": 450,
                "New York, NY": 380,
                "Remote": 290
            },
            "companies": {
                "Google": 45,
                "Apple": 38,
                "Microsoft": 32
            },
            "salary_ranges": {
                "$100k - $150k": 420,
                "$150k - $200k": 380,
                "$75k - $100k": 290
            },
            "remote_work": {
                "Remote": 290,
                "On-site": 960
            },
            "posted_dates": {
                "Today": 45,
                "Last 3 days": 120,
                "Last week": 280
            }
        },
        "message": "Facets calculated successfully"
    }
    ```
    """
    try:
        # Convert query parameters to search criteria
        from datetime import datetime, timedelta

        posted_after = None
        if posted_within:
            posted_after = datetime.utcnow() - timedelta(days=posted_within)

        criteria = JobSearchCriteria(
            query=q,
            title=title,
            location=location,
            company=company,
            posted_after=posted_after,
            min_quality_score=min_quality_score,
            exclude_spam=exclude_spam,
            # Don't include filters we're counting
            limit=1,  # We don't need actual results, just counts
            offset=0
        )

        # Calculate facets
        facets = await facet_service.calculate_facets(criteria, db_session)

        return {
            "status": True,
            "data": facets,
            "message": "Facets calculated successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate facets: {str(e)}")


@router.get("/facets/popular-terms")
@log_api_call()
@standardize_response(success_message="Popular search terms retrieved successfully")
async def get_popular_search_terms(
    limit: int = Query(10, ge=1, le=50, description="Number of terms to return"),
    db_session: AsyncSession = Depends(lambda: db.session)
) -> dict:
    """
    Get popular search terms for autocomplete enhancement.

    Returns frequently searched terms with their usage counts to improve
    search suggestions and user experience.
    """
    try:
        popular_terms = await facet_service.get_popular_search_terms(limit, db_session)

        return {
            "status": True,
            "data": popular_terms,
            "message": "Popular search terms retrieved successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get popular terms: {str(e)}")


@router.get("/facets/trending-skills")
@log_api_call()
@standardize_response(success_message="Trending skills retrieved successfully")
async def get_trending_skills(
    limit: int = Query(20, ge=1, le=100, description="Number of skills to return"),
    db_session: AsyncSession = Depends(lambda: db.session)
) -> dict:
    """
    Get trending skills from recent job postings.

    Returns skills that are frequently mentioned in recent job postings,
    helping users understand market demand and optimize their search.
    """
    try:
        trending_skills = await facet_service.get_trending_skills(limit, db_session)

        return {
            "status": True,
            "data": trending_skills,
            "message": "Trending skills retrieved successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trending skills: {str(e)}")


@router.get("/facets/stats")
@log_api_call()
@standardize_response(success_message="Search statistics retrieved successfully")
async def get_search_statistics(
    db_session: AsyncSession = Depends(lambda: db.session)
) -> dict:
    """
    Get overall search and job statistics.

    Returns general statistics about the job database to provide context
    for search results and platform health.
    """
    try:
        from sqlalchemy import text

        # Get basic statistics
        stats_query = """
            SELECT
                COUNT(*) as total_active_jobs,
                COUNT(DISTINCT company_id) as total_companies,
                COUNT(*) FILTER (WHERE posted_date >= CURRENT_DATE - INTERVAL '7 days') as jobs_this_week,
                COUNT(*) FILTER (WHERE posted_date >= CURRENT_DATE - INTERVAL '30 days') as jobs_this_month,
                COUNT(*) FILTER (WHERE is_remote = true) as remote_jobs,
                COUNT(*) FILTER (WHERE salary_disclosed = true) as jobs_with_salary,
                AVG(quality_score) as avg_quality_score
            FROM jobs
            WHERE status = 'active'
        """

        result = await db_session.execute(text(stats_query))
        row = result.fetchone()

        stats = {
            "total_active_jobs": row.total_active_jobs,
            "total_companies": row.total_companies,
            "jobs_this_week": row.jobs_this_week,
            "jobs_this_month": row.jobs_this_month,
            "remote_jobs": row.remote_jobs,
            "jobs_with_salary": row.jobs_with_salary,
            "avg_quality_score": round(float(row.avg_quality_score), 2) if row.avg_quality_score else 0,
            "salary_disclosure_rate": round((row.jobs_with_salary / row.total_active_jobs) * 100, 1) if row.total_active_jobs > 0 else 0,
            "remote_job_percentage": round((row.remote_jobs / row.total_active_jobs) * 100, 1) if row.total_active_jobs > 0 else 0
        }

        return {
            "status": True,
            "data": stats,
            "message": "Search statistics retrieved successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")