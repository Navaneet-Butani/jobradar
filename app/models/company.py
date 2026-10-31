"""Company-related data models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl, validator

from .base import TimestampMixin
from .common import CompanySize


class CompanyInfo(BaseModel):
    """Basic company information extracted from job data."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Company name")
    normalized_name: Optional[str] = Field(None, max_length=255, description="Normalized company name")
    website: Optional[HttpUrl] = Field(None, description="Company website URL")
    logo_url: Optional[HttpUrl] = Field(None, description="Company logo URL")
    description: Optional[str] = Field(None, description="Company description")
    industry: Optional[str] = Field(None, max_length=100, description="Company industry")
    location: Optional[str] = Field(None, max_length=255, description="Company headquarters location")
    size: Optional[CompanySize] = Field(None, description="Company size category")
    employee_count: Optional[int] = Field(None, ge=0, description="Number of employees")
    founded_year: Optional[int] = Field(None, ge=1800, le=2030, description="Year company was founded")
    
    @validator('name', 'normalized_name')
    def validate_name(cls, v):
        """Validate company names."""
        if v:
            return v.strip()
        return v


class CompanyMatch(BaseModel):
    """Result of company matching operation."""
    
    company_id: Optional[int] = Field(None, description="Matched company ID")
    confidence_score: float = Field(ge=0, le=1, description="Matching confidence score")
    match_type: str = Field(..., description="Type of match (exact, fuzzy, new)")
    matched_name: Optional[str] = Field(None, description="Name that was matched")
    alternative_matches: List[dict] = Field(default_factory=list, description="Alternative company matches")


class CompanyNormalizationResult(BaseModel):
    """Result of company name normalization."""
    
    original_name: str = Field(..., description="Original company name")
    normalized_name: str = Field(..., description="Normalized company name")
    removed_suffixes: List[str] = Field(default_factory=list, description="Corporate suffixes removed")
    applied_rules: List[str] = Field(default_factory=list, description="Normalization rules applied")
    aliases_found: List[str] = Field(default_factory=list, description="Known aliases found")


class CompanyCreate(BaseModel):
    """Model for creating new companies."""
    
    name: str = Field(..., min_length=1, max_length=255)
    normalized_name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=255)
    website: Optional[HttpUrl] = None
    career_page_url: Optional[HttpUrl] = None
    logo_url: Optional[HttpUrl] = None
    description: Optional[str] = None
    headquarters: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    founded_year: Optional[int] = Field(None, ge=1800, le=2030)
    employee_count: Optional[int] = Field(None, ge=0)
    data_quality_score: float = Field(default=50.0, ge=0, le=100)


class CompanyUpdate(BaseModel):
    """Model for updating existing companies."""
    
    website: Optional[HttpUrl] = None
    career_page_url: Optional[HttpUrl] = None
    logo_url: Optional[HttpUrl] = None
    description: Optional[str] = None
    headquarters: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    founded_year: Optional[int] = Field(None, ge=1800, le=2030)
    employee_count: Optional[int] = Field(None, ge=0)
    glassdoor_rating: Optional[Decimal] = Field(None, ge=0, le=5, decimal_places=2)
    linkedin_url: Optional[HttpUrl] = None
    twitter_url: Optional[HttpUrl] = None
    linkedin_company_id: Optional[str] = Field(None, max_length=100)
    data_quality_score: Optional[float] = Field(None, ge=0, le=100)
    total_jobs_posted: Optional[int] = Field(None, ge=0)
    active_jobs_count: Optional[int] = Field(None, ge=0)
    last_job_posted_at: Optional[datetime] = None


class CompanyStats(BaseModel):
    """Company statistics and metrics."""
    
    company_id: int = Field(..., description="Company ID")
    total_jobs_posted: int = Field(ge=0, description="Total jobs posted")
    active_jobs_count: int = Field(ge=0, description="Currently active jobs")
    avg_quality_score: Optional[float] = Field(None, ge=0, le=100, description="Average job quality score")
    last_job_posted_at: Optional[datetime] = Field(None, description="When last job was posted")
    job_posting_frequency: Optional[float] = Field(None, ge=0, description="Jobs per month average")
    top_skills: List[str] = Field(default_factory=list, description="Most common skills in job postings")
    salary_ranges: dict = Field(default_factory=dict, description="Salary range statistics")


class CompanyEnrichment(BaseModel):
    """External data enrichment for companies."""
    
    company_id: int = Field(..., description="Company ID")
    enrichment_source: str = Field(..., description="Source of enrichment data")
    enrichment_data: dict = Field(..., description="Enriched company data")
    confidence_score: float = Field(ge=0, le=1, description="Confidence in enrichment data")
    enriched_at: datetime = Field(default_factory=datetime.utcnow, description="When data was enriched")
    
    
class CompanySearchCriteria(BaseModel):
    """Criteria for searching companies."""
    
    name: Optional[str] = Field(None, min_length=1, description="Company name search")
    industry: Optional[str] = Field(None, description="Industry filter")
    size: Optional[CompanySize] = Field(None, description="Company size filter")
    location: Optional[str] = Field(None, description="Location filter")
    min_employees: Optional[int] = Field(None, ge=0, description="Minimum employee count")
    max_employees: Optional[int] = Field(None, ge=0, description="Maximum employee count")
    has_jobs: Optional[bool] = Field(None, description="Filter companies with active jobs")
    min_quality_score: Optional[float] = Field(None, ge=0, le=100, description="Minimum data quality score")