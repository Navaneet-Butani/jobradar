"""Job API schemas for request and response models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator

from ...models.common import EmploymentType, ExperienceLevel, Currency


class JobSearchRequest(BaseModel):
    """Request model for job search."""

    # Text search
    q: Optional[str] = Field(None, description="Search query", max_length=200)
    title: Optional[str] = Field(None, description="Job title filter", max_length=200)
    company: Optional[str] = Field(None, description="Company name filter", max_length=200)
    location: Optional[str] = Field(None, description="Location filter", max_length=200)

    # Job characteristics
    employment_types: Optional[List[EmploymentType]] = Field(None, description="Employment types")
    experience_levels: Optional[List[ExperienceLevel]] = Field(None, description="Experience levels")
    is_remote: Optional[bool] = Field(None, description="Remote work filter")

    # Salary filters
    min_salary: Optional[Decimal] = Field(None, ge=0, description="Minimum salary")
    max_salary: Optional[Decimal] = Field(None, ge=0, description="Maximum salary")
    salary_currency: Optional[Currency] = Field(Currency.USD, description="Salary currency")
    salary_disclosed_only: Optional[bool] = Field(False, description="Only jobs with disclosed salary")

    # Skills
    required_skills: Optional[List[str]] = Field(None, description="Required skills")
    preferred_skills: Optional[List[str]] = Field(None, description="Preferred skills")

    # Date filters
    posted_within_days: Optional[int] = Field(None, ge=1, le=365, description="Posted within N days")

    # Quality filters
    min_quality_score: Optional[float] = Field(None, ge=0, le=100, description="Minimum quality score")
    exclude_spam: bool = Field(True, description="Exclude suspected spam")

    # Pagination and sorting
    page: int = Field(1, ge=1, description="Page number")
    limit: int = Field(20, ge=1, le=100, description="Results per page")
    sort_by: str = Field("relevance", description="Sort field")
    sort_order: str = Field("desc", pattern="^(asc|desc)$", description="Sort order")

    class Config:
        json_schema_extra = {
            "example": {
                "q": "python developer",
                "location": "San Francisco",
                "employment_types": ["full-time"],
                "is_remote": False,
                "min_salary": 80000,
                "max_salary": 150000,
                "salary_currency": "USD",
                "required_skills": ["Python", "Django"],
                "posted_within_days": 30,
                "page": 1,
                "limit": 20,
                "sort_by": "relevance",
                "sort_order": "desc"
            }
        }


class CompanyInfo(BaseModel):
    """Company information in job response."""

    id: Optional[int] = Field(None, description="Company ID")
    name: str = Field(..., description="Company name")
    slug: Optional[str] = Field(None, description="URL-safe company slug")
    logo_url: Optional[str] = Field(None, description="Company logo URL")
    website: Optional[str] = Field(None, description="Company website")
    industry: Optional[str] = Field(None, description="Industry")
    headquarters: Optional[str] = Field(None, description="Headquarters location")
    ats_type: Optional[str] = Field(None, description="ATS behind the company's own careers page")
    tagline: Optional[str] = Field(None, description="One-line company pitch")
    description: Optional[str] = Field(None, description="Company blurb, as published by the source")
    founded_year: Optional[int] = Field(None, description="Year founded")
    employee_count: Optional[int] = Field(None, description="Headcount, when given as a number")
    employee_range: Optional[str] = Field(None, description="Headcount band, e.g. 1001-5000")
    rating: Optional[float] = Field(None, description="Employer rating out of 5, as published by the source")
    rating_count: Optional[int] = Field(None, description="Number of reviews behind the rating")
    rating_url: Optional[str] = Field(None, description="Where the rating can be read in full")
    rating_source: Optional[str] = Field(None, description="Who publishes the rating, e.g. ambitionbox")


class LocationInfo(BaseModel):
    """Location information in job response."""

    raw: Optional[str] = Field(None, description="Raw location string")
    city: Optional[str] = Field(None, description="City")
    country: str = Field(..., description="Country")
    is_remote: bool = Field(False, description="Remote work available")


class SalaryInfo(BaseModel):
    """Salary information in job response."""

    min: Optional[float] = Field(None, description="Minimum salary")
    max: Optional[float] = Field(None, description="Maximum salary")
    currency: str = Field("USD", description="Salary currency")
    disclosed: bool = Field(False, description="Whether salary is disclosed")


class JobSummary(BaseModel):
    """Job summary for search results."""

    id: int = Field(..., description="Job ID")
    uuid: str = Field(..., description="Job UUID")
    title: str = Field(..., description="Job title")
    company: CompanyInfo = Field(..., description="Company information")
    location: LocationInfo = Field(..., description="Location information")
    employment_type: Optional[str] = Field(None, description="Employment type")
    experience_level: Optional[str] = Field(None, description="Experience level")
    salary: SalaryInfo = Field(..., description="Salary information")
    posted_date: Optional[str] = Field(None, description="Posted date (ISO format)")
    apply_url: str = Field(..., description="Application URL")
    skills_required: List[str] = Field(default_factory=list, description="Required skills")
    skills_preferred: List[str] = Field(default_factory=list, description="Preferred skills")
    quality_score: float = Field(..., description="Job quality score")
    relevance_score: Optional[float] = Field(None, description="Search relevance score")
    views_count: int = Field(0, description="Number of views")
    is_saved: bool = Field(False, description="Whether user saved this job")


class JobDetail(JobSummary):
    """Detailed job information."""

    description: Optional[str] = Field(None, description="Job description")
    requirements: Optional[str] = Field(None, description="Job requirements")
    responsibilities: Optional[str] = Field(None, description="Job responsibilities")
    benefits: List[str] = Field(default_factory=list, description="Job benefits")
    apply_email: Optional[str] = Field(None, description="Application email")
    application_deadline: Optional[str] = Field(None, description="Application deadline")
    clicks_count: int = Field(0, description="Number of clicks")
    applications_count: int = Field(0, description="Number of applications")

    # Provenance — which board this came from, and when we actually saw it.
    # `posted_date` is the employer's claim; on aggregators it is often days
    # older than first_seen_at, or missing entirely.
    source_name: Optional[str] = Field(None, description="Board this posting was ingested from")
    source_url: Optional[str] = Field(None, description="Original posting URL on that board")
    first_seen_at: Optional[str] = Field(None, description="When JobRadar first ingested this posting")
    last_seen_at: Optional[str] = Field(None, description="Last time the posting was still live at source")
    remote_scope: Optional[str] = Field(None, description="india_only | global | us_only | …")
    min_exp_years: Optional[int] = Field(None, description="Minimum years of experience asked for")
    max_exp_years: Optional[int] = Field(None, description="Maximum years of experience asked for")
    department: Optional[str] = Field(None, description="Team or department")
    work_arrangement: Optional[str] = Field(None, description="Onsite / hybrid / remote")
    how_to_apply: Optional[str] = Field(None, description="Application instructions given in the posting")

    # Who posted it and how crowded it already is, per the source board. Both
    # are missing on sources that do not publish them (most of them).
    poster_name: Optional[str] = Field(None, description="Person or team who posted the job")
    poster_title: Optional[str] = Field(None, description="Their role, e.g. Senior IT Recruiter")
    source_applicant_count: Optional[int] = Field(None, description="Applicants the source reports")
    source_view_count: Optional[int] = Field(None, description="Views the source reports")


class SearchMetadata(BaseModel):
    """Search result metadata."""

    total: int = Field(..., description="Total number of results")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Results per page")
    pages: int = Field(..., description="Total number of pages")
    query_time_ms: int = Field(..., description="Query execution time in milliseconds")
    filters_applied: List[str] = Field(..., description="List of applied filters")
    has_next: bool = Field(..., description="Whether there are more results")
    has_previous: bool = Field(..., description="Whether there are previous results")


class JobSearchResponse(BaseModel):
    """Response model for job search."""

    status: bool = Field(True, description="Request status")
    data: List[JobSummary] = Field(..., description="Job search results")
    metadata: SearchMetadata = Field(..., description="Search metadata")
    message: str = Field("Search completed successfully", description="Response message")


class JobDetailResponse(BaseModel):
    """Response model for job detail."""

    status: bool = Field(True, description="Request status")
    data: JobDetail = Field(..., description="Job details")
    message: str = Field("Job details retrieved successfully", description="Response message")


class AutocompleteRequest(BaseModel):
    """Request model for autocomplete suggestions."""

    q: str = Field(..., min_length=1, max_length=100, description="Search query")
    type: str = Field("all", pattern="^(all|title|company|location|skills)$", description="Suggestion type")
    limit: int = Field(10, ge=1, le=50, description="Maximum number of suggestions")

    class Config:
        json_schema_extra = {
            "example": {
                "q": "python",
                "type": "title",
                "limit": 10
            }
        }


class AutocompleteResponse(BaseModel):
    """Response model for autocomplete suggestions."""

    status: bool = Field(True, description="Request status")
    data: List[str] = Field(..., description="Autocomplete suggestions")
    message: str = Field("Suggestions retrieved successfully", description="Response message")


class PopularJobsResponse(BaseModel):
    """Response model for popular jobs."""

    status: bool = Field(True, description="Request status")
    data: List[JobSummary] = Field(..., description="Popular jobs")
    message: str = Field("Popular jobs retrieved successfully", description="Response message")


class RecentJobsResponse(BaseModel):
    """Response model for recent jobs."""

    status: bool = Field(True, description="Request status")
    data: List[JobSummary] = Field(..., description="Recent jobs")
    message: str = Field("Recent jobs retrieved successfully", description="Response message")


class RecommendedJobsResponse(BaseModel):
    """Response model for recommended jobs."""

    status: bool = Field(True, description="Request status")
    data: List[JobSummary] = Field(..., description="Recommended jobs")
    message: str = Field("Recommended jobs retrieved successfully", description="Response message")


class JobAnalyticsRequest(BaseModel):
    """Request model for tracking job analytics."""

    action: str = Field(..., pattern="^(view|click|apply)$", description="Analytics action")
    user_agent: Optional[str] = Field(None, description="User agent string")
    referrer: Optional[str] = Field(None, description="Referrer URL")

    class Config:
        json_schema_extra = {
            "example": {
                "action": "click",
                "user_agent": "Mozilla/5.0...",
                "referrer": "https://example.com"
            }
        }