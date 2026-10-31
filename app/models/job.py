"""Job-related data models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, validator

from .base import TimestampMixin, ValidationResult, DeduplicationResult
from .common import (
    EmploymentType, ExperienceLevel, WorkArrangement, 
    SalaryPeriod, Currency, JobStatus, SkillCategory, CompanyId, SourceId
)
from .company import CompanyInfo


class LocationInfo(BaseModel):
    """Location information with parsing and normalization."""
    
    raw_location: Optional[str] = Field(None, description="Raw location string from source")
    city: Optional[str] = Field(None, max_length=100, description="Parsed city name")
    state_province: Optional[str] = Field(None, max_length=100, description="State or province")
    country: str = Field(default="Unknown", max_length=50, description="Country")
    country_code: Optional[str] = Field(None, max_length=2, description="ISO country code")
    is_remote: bool = Field(default=False, description="Whether job is remote")
    work_arrangement: Optional[WorkArrangement] = Field(None, description="Work arrangement type")
    remote_scope: Optional[str] = Field(None, description="Region a remote job is open to: india_only/global/us_only/eu_only/uk_only")
    timezone: Optional[str] = Field(None, description="Timezone if specified")
    
    # Coordinates for location-based searches
    latitude: Optional[float] = Field(None, ge=-90, le=90, description="Latitude coordinate")
    longitude: Optional[float] = Field(None, ge=-180, le=180, description="Longitude coordinate")
    
    @classmethod
    def parse_location(cls, raw_location: str) -> "LocationInfo":
        """Parse raw location string into structured location info."""
        # This will be implemented in the service layer
        return cls(raw_location=raw_location)
    
    @validator('city', 'state_province')
    def normalize_location_names(cls, v):
        """Normalize location names."""
        if v:
            return v.strip().title()
        return v


class SalaryInfo(BaseModel):
    """Salary information with multi-currency support."""
    
    raw_salary: Optional[str] = Field(None, description="Raw salary string from source")
    min_salary: Optional[Decimal] = Field(None, ge=0, description="Minimum salary")
    max_salary: Optional[Decimal] = Field(None, ge=0, description="Maximum salary") 
    currency: Currency = Field(default=Currency.USD, description="Salary currency")
    period: SalaryPeriod = Field(default=SalaryPeriod.YEAR, description="Salary period")
    is_disclosed: bool = Field(default=False, description="Whether salary is disclosed")
    is_negotiable: bool = Field(default=False, description="Whether salary is negotiable")
    
    # Additional compensation
    bonus_info: Optional[str] = Field(None, description="Bonus information")
    equity_info: Optional[str] = Field(None, description="Equity information")
    benefits_value: Optional[Decimal] = Field(None, ge=0, description="Estimated benefits value")
    
    @validator('max_salary')
    def validate_salary_range(cls, v, values):
        """Ensure max salary is greater than min salary."""
        min_salary = values.get('min_salary')
        if v is not None and min_salary is not None and v < min_salary:
            raise ValueError('max_salary must be greater than or equal to min_salary')
        return v
    
    @classmethod
    def parse_salary(cls, raw_salary: str) -> "SalaryInfo":
        """Parse raw salary string into structured salary info."""
        # This will be implemented in the service layer
        return cls(raw_salary=raw_salary)


class SkillInfo(BaseModel):
    """Skill information extracted from job descriptions."""
    
    name: str = Field(..., description="Skill name")
    category: Optional[SkillCategory] = Field(None, description="Skill category")
    is_required: bool = Field(default=True, description="Whether skill is required")
    confidence_score: float = Field(ge=0, le=1, description="Extraction confidence")
    context: Optional[str] = Field(None, description="Context where skill was mentioned")
    
    
class JobBase(BaseModel):
    """Base job model with common fields."""
    
    title: str = Field(..., min_length=1, max_length=500, description="Job title")
    company_name: str = Field(..., min_length=1, max_length=255, description="Company name")
    location: Optional[LocationInfo] = Field(None, description="Job location")
    is_remote: bool = Field(default=False, description="Whether job is remote")
    employment_type: Optional[EmploymentType] = Field(None, description="Employment type")
    experience_level: Optional[ExperienceLevel] = Field(None, description="Experience level required")
    min_exp_years: Optional[int] = Field(None, ge=0, description="Minimum years of experience required")
    max_exp_years: Optional[int] = Field(None, ge=0, description="Maximum years of experience required")
    salary: Optional[SalaryInfo] = Field(None, description="Salary information")
    posted_date: Optional[datetime] = Field(None, description="Date job was posted")
    apply_url: str = Field(..., description="URL to apply for job")
    
    @validator('title')
    def validate_title(cls, v):
        """Validate and normalize job title."""
        return v.strip()


class RawJob(BaseModel):
    """Raw job data from external sources."""
    
    source_id: SourceId = Field(..., description="Source ID")
    external_id: str = Field(..., max_length=255, description="External job ID")
    raw_data: Dict[str, Any] = Field(..., description="Raw job data")
    source_url: Optional[str] = Field(None, max_length=1000, description="Source URL")
    fetched_at: datetime = Field(default_factory=datetime.utcnow, description="Fetch timestamp")
    
    def to_standard_job(self, field_mapping: Dict[str, List[str]]) -> "StandardJob":
        """Convert raw job data to standardized job format."""
        # This will be implemented in the service layer
        pass


class StandardJob(JobBase):
    """Standardized job model after normalization."""

    # Identity — set by sources (like RemoteOK) whose parser resolves these
    # itself instead of going through the generic FieldExtractor/RawJob path.
    source_id: Optional[SourceId] = Field(None, description="Source ID")
    external_id: Optional[str] = Field(None, max_length=255, description="External job ID")

    # Enhanced fields
    normalized_title: Optional[str] = Field(None, max_length=255, description="Normalized job title")
    company: Optional[CompanyInfo] = Field(None, description="Company information")
    department: Optional[str] = Field(None, max_length=100, description="Department")
    
    # Job details
    description: Optional[str] = Field(None, description="Job description")
    requirements: Optional[str] = Field(None, description="Job requirements")
    responsibilities: Optional[str] = Field(None, description="Job responsibilities")
    benefits: List[str] = Field(default_factory=list, description="Job benefits")
    
    # Skills
    skills_required: List[SkillInfo] = Field(default_factory=list, description="Required skills")
    skills_preferred: List[SkillInfo] = Field(default_factory=list, description="Preferred skills")
    skills_extracted: List[str] = Field(default_factory=list, description="All extracted skills")
    
    # Application details
    apply_email: Optional[str] = Field(None, description="Email to apply")
    application_deadline: Optional[datetime] = Field(None, description="Application deadline")
    contact_emails: List[str] = Field(default_factory=list, description="Role-based contact emails (careers@, hr@, etc.) harvested from the description")
    
    # Processing metadata
    content_hash: Optional[str] = Field(None, description="Content hash for deduplication")
    quality_score: Optional[float] = Field(None, ge=0, le=100, description="Quality score")
    confidence_score: Optional[float] = Field(None, ge=0, le=1, description="Processing confidence")
    
    def generate_content_hash(self) -> str:
        """Generate content hash for deduplication."""
        # This will be implemented in the service layer
        pass
        
    def calculate_quality_score(self) -> float:
        """Calculate quality score based on completeness and content."""
        # This will be implemented in the service layer
        pass
        
    def extract_skills(self) -> List[str]:
        """Extract skills from description and requirements."""
        # This will be implemented in the service layer
        pass


class ProcessedJob(StandardJob, TimestampMixin):
    """Fully processed job ready for database storage."""
    
    # Database fields
    id: Optional[int] = Field(None, description="Database ID")
    uuid: Optional[str] = Field(None, description="UUID for external references")
    source_id: SourceId = Field(..., description="Source ID")
    external_id: str = Field(..., description="External job ID")
    company_id: Optional[CompanyId] = Field(None, description="Company ID")
    
    # Status and tracking
    status: JobStatus = Field(default=JobStatus.ACTIVE, description="Job status")
    first_seen_at: datetime = Field(default_factory=datetime.utcnow, description="First seen timestamp")
    last_seen_at: datetime = Field(default_factory=datetime.utcnow, description="Last seen timestamp")
    last_updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    
    # Validation and quality
    is_valid_link: bool = Field(default=True, description="Whether apply URL is valid")
    spam_score: float = Field(default=0.0, ge=0, le=100, description="Spam likelihood score")
    validation_result: Optional[ValidationResult] = Field(None, description="Validation details")
    deduplication_result: Optional[DeduplicationResult] = Field(None, description="Deduplication details")
    
    # Analytics
    views_count: int = Field(default=0, ge=0, description="Number of views")
    clicks_count: int = Field(default=0, ge=0, description="Number of clicks")
    applications_count: int = Field(default=0, ge=0, description="Number of applications")
    
    # Search optimization
    search_vector: Optional[str] = Field(None, description="Full-text search vector")


class JobSearchCriteria(BaseModel):
    """Criteria for searching jobs."""
    
    # Basic filters
    query: Optional[str] = Field(None, min_length=1, description="Search query")
    title: Optional[str] = Field(None, description="Job title filter")
    company: Optional[str] = Field(None, description="Company name filter")
    location: Optional[str] = Field(None, description="Location filter")
    
    # Job characteristics
    employment_types: Optional[List[EmploymentType]] = Field(None, description="Employment types")
    experience_levels: Optional[List[ExperienceLevel]] = Field(None, description="Experience levels")
    is_remote: Optional[bool] = Field(None, description="Remote work filter")
    
    # Salary filters
    min_salary: Optional[Decimal] = Field(None, ge=0, description="Minimum salary")
    max_salary: Optional[Decimal] = Field(None, ge=0, description="Maximum salary")
    salary_currency: Optional[Currency] = Field(None, description="Salary currency")
    salary_disclosed_only: Optional[bool] = Field(None, description="Only jobs with disclosed salary")
    
    # Skills filters
    required_skills: Optional[List[str]] = Field(None, description="Required skills")
    preferred_skills: Optional[List[str]] = Field(None, description="Preferred skills")
    
    # Date filters
    posted_after: Optional[datetime] = Field(None, description="Posted after date")
    posted_before: Optional[datetime] = Field(None, description="Posted before date")
    
    # Quality filters
    min_quality_score: Optional[float] = Field(None, ge=0, le=100, description="Minimum quality score")
    exclude_spam: bool = Field(default=True, description="Exclude suspected spam")
    
    # Pagination
    limit: int = Field(default=20, ge=1, le=100, description="Number of results")
    offset: int = Field(default=0, ge=0, description="Results offset")
    
    # Sorting
    sort_by: str = Field(default="posted_date", description="Sort field")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$", description="Sort order")


class JobAnalytics(BaseModel):
    """Job analytics and metrics."""
    
    job_id: int = Field(..., description="Job ID")
    
    # View metrics
    total_views: int = Field(ge=0, description="Total views")
    unique_views: int = Field(ge=0, description="Unique views")
    avg_view_duration: Optional[float] = Field(None, ge=0, description="Average view duration in seconds")
    
    # Click metrics
    total_clicks: int = Field(ge=0, description="Total clicks")
    click_through_rate: Optional[float] = Field(None, ge=0, le=1, description="Click-through rate")
    
    # Application metrics
    total_applications: int = Field(ge=0, description="Total applications")
    application_rate: Optional[float] = Field(None, ge=0, le=1, description="Application rate")
    
    # Engagement metrics
    save_count: int = Field(ge=0, description="Times job was saved")
    share_count: int = Field(ge=0, description="Times job was shared")
    
    # Performance over time
    daily_views: List[Dict[str, int]] = Field(default_factory=list, description="Daily view counts")
    peak_interest_date: Optional[datetime] = Field(None, description="Date of peak interest")
    
    # Comparative metrics
    industry_percentile: Optional[float] = Field(None, ge=0, le=100, description="Performance vs industry")
    company_percentile: Optional[float] = Field(None, ge=0, le=100, description="Performance vs company jobs")


class JobRecommendation(BaseModel):
    """Job recommendation for a user."""
    
    job_id: int = Field(..., description="Recommended job ID")
    user_id: int = Field(..., description="User ID")
    relevance_score: float = Field(ge=0, le=1, description="Relevance score")
    recommendation_reason: str = Field(..., description="Why job was recommended")
    recommendation_factors: List[str] = Field(default_factory=list, description="Factors used in recommendation")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Recommendation timestamp")
    
    # Optional job details for display
    job_title: Optional[str] = Field(None, description="Job title")
    company_name: Optional[str] = Field(None, description="Company name")
    location: Optional[str] = Field(None, description="Job location")
    salary_range: Optional[str] = Field(None, description="Salary range string")