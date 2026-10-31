"""Job source and field mapping models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List, Any, Union
from pydantic import BaseModel, Field, HttpUrl, validator

from .base import TimestampMixin
from .common import ProcessingStatus


class FieldMapping(BaseModel):
    """Configuration for mapping fields from different job sources."""
    
    # Core job fields
    title: List[str] = Field(default_factory=lambda: ["title", "job_title", "position", "role"])
    company: List[str] = Field(default_factory=lambda: ["company", "company_name", "employer", "organization"])
    location: List[str] = Field(default_factory=lambda: ["location", "job_location", "city", "address"])
    description: List[str] = Field(default_factory=lambda: ["description", "job_description", "details", "summary"])
    
    # Salary fields
    salary: List[str] = Field(default_factory=lambda: ["salary", "compensation", "pay", "wage"])
    salary_min: List[str] = Field(default_factory=lambda: ["salary_min", "min_salary", "salary_from"])
    salary_max: List[str] = Field(default_factory=lambda: ["salary_max", "max_salary", "salary_to"])
    salary_currency: List[str] = Field(default_factory=lambda: ["currency", "salary_currency"])
    salary_period: List[str] = Field(default_factory=lambda: ["salary_period", "pay_period", "frequency"])
    
    # Job characteristics
    employment_type: List[str] = Field(default_factory=lambda: ["employment_type", "job_type", "type"])
    experience_level: List[str] = Field(default_factory=lambda: ["experience_level", "seniority", "level"])
    # Years of experience, when the source states them outright. No defaults on
    # purpose: the only source that carries them (Hirist) names them `min`/`max`,
    # which is far too generic to guess at across every other payload shape.
    min_exp_years: List[str] = Field(default_factory=list)
    max_exp_years: List[str] = Field(default_factory=list)
    department: List[str] = Field(default_factory=lambda: ["department", "team", "division"])
    
    # Application details
    apply_url: List[str] = Field(default_factory=lambda: ["apply_url", "application_url", "url", "link"])
    apply_email: List[str] = Field(default_factory=lambda: ["apply_email", "contact_email", "email"])
    
    # Skills and requirements
    skills_required: List[str] = Field(default_factory=lambda: ["skills", "requirements", "required_skills"])
    skills_preferred: List[str] = Field(default_factory=lambda: ["preferred_skills", "nice_to_have", "bonus_skills"])
    
    # Additional fields
    benefits: List[str] = Field(default_factory=lambda: ["benefits", "perks", "compensation_benefits"])
    posted_date: List[str] = Field(default_factory=lambda: ["posted_date", "date_posted", "created_date"])
    deadline: List[str] = Field(default_factory=lambda: ["deadline", "application_deadline", "expires_at"])


class ExtractionRules(BaseModel):
    """Rules for extracting specific information from job data."""
    
    # Remote work indicators
    remote_keywords: List[str] = Field(
        default_factory=lambda: [
            "remote", "work from home", "wfh", "distributed", "anywhere", 
            "telecommute", "virtual", "home-based", "location independent"
        ]
    )
    
    # Experience level patterns
    experience_patterns: List[str] = Field(
        default_factory=lambda: [
            r"\b(\d+)\s*-?\s*(\d+)?\s*years?\b",
            r"\bsenior\b", r"\bjunior\b", r"\bentry[-\s]?level\b",
            r"\blead\b", r"\bprincipal\b", r"\bdirector\b"
        ]
    )
    
    # Salary extraction patterns
    salary_patterns: List[str] = Field(
        default_factory=lambda: [
            r"[\$£€¥]\s*([0-9,]+)\s*-?\s*[\$£€¥]?\s*([0-9,]+)?",
            r"([0-9,]+)\s*-\s*([0-9,]+)\s*(USD|EUR|GBP|CAD|AUD)",
            r"salary:?\s*[\$£€¥]?\s*([0-9,]+)"
        ]
    )
    
    # Employment type keywords
    employment_type_keywords: Dict[str, List[str]] = Field(
        default_factory=lambda: {
            "full_time": ["full time", "full-time", "permanent", "ft"],
            "part_time": ["part time", "part-time", "pt"],
            "contract": ["contract", "contractor", "consulting", "freelance"],
            "internship": ["intern", "internship", "graduate", "trainee"],
            "temporary": ["temporary", "temp", "seasonal"]
        }
    )
    
    # Skills to exclude (common words that aren't skills)
    skill_exclusions: List[str] = Field(
        default_factory=lambda: [
            "experience", "knowledge", "ability", "skills", "requirements",
            "years", "work", "team", "company", "position", "role"
        ]
    )


class SourceConfig(BaseModel):
    """Configuration for a job source."""
    
    source_id: int = Field(..., description="Source ID")
    name: str = Field(..., description="Source name")
    source_type: str = Field(..., description="Source type (api, scraping, etc.)")
    base_url: Optional[HttpUrl] = Field(None, description="Base URL for the source")
    is_active: bool = Field(True, description="Whether source is active")
    
    # Field mapping configuration
    field_mapping: FieldMapping = Field(default_factory=FieldMapping)
    extraction_rules: ExtractionRules = Field(default_factory=ExtractionRules)
    
    # API configuration (if applicable)
    api_config: Optional[Dict[str, Any]] = Field(None, description="API-specific configuration")
    
    # Scraping configuration (if applicable)  
    scraping_config: Optional[Dict[str, Any]] = Field(None, description="Scraping-specific configuration")
    
    # Rate limiting and quotas
    hourly_quota: int = Field(default=100, ge=0)
    daily_quota: int = Field(default=1000, ge=0)
    monthly_quota: int = Field(default=10000, ge=0)
    
    # Quality settings
    min_quality_score: float = Field(default=30.0, ge=0, le=100)
    max_spam_score: float = Field(default=70.0, ge=0, le=100)
    
    # Processing settings
    batch_size: int = Field(default=100, ge=1, le=1000)
    retry_attempts: int = Field(default=3, ge=0, le=10)
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class RawJobData(BaseModel):
    """Raw job data as received from a source."""
    
    source_id: int = Field(..., description="Source ID")
    external_id: str = Field(..., description="External job ID from source")
    raw_data: Dict[str, Any] = Field(..., description="Raw job data from source")
    source_url: Optional[str] = Field(None, description="URL where job was found")
    fetched_at: datetime = Field(default_factory=datetime.utcnow, description="When data was fetched")
    
    def extract_field(self, field_mapping: FieldMapping, field_name: str) -> Optional[Any]:
        """Extract a field value using the field mapping."""
        possible_keys = getattr(field_mapping, field_name, [])
        
        for key in possible_keys:
            # Support nested keys with dot notation
            if '.' in key:
                value = self._get_nested_value(self.raw_data, key.split('.'))
            else:
                value = self.raw_data.get(key)
                
            if value is not None and value != "":
                return value
        
        return None
    
    def _get_nested_value(self, data: Dict[str, Any], keys: List[str]) -> Optional[Any]:
        """Get value from nested dictionary using key path."""
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current


class SourceFetchRequest(BaseModel):
    """Request to fetch jobs from a source."""
    
    source_id: int = Field(..., description="Source ID to fetch from")
    batch_uuid: Optional[str] = Field(None, description="Batch UUID for tracking")
    limit: Optional[int] = Field(None, ge=1, le=10000, description="Maximum jobs to fetch")
    offset: Optional[int] = Field(None, ge=0, description="Offset for pagination")
    filters: Optional[Dict[str, Any]] = Field(None, description="Additional filters")


class SourceFetchResult(BaseModel):
    """Result of fetching jobs from a source."""
    
    source_id: int = Field(..., description="Source ID")
    batch_uuid: str = Field(..., description="Batch UUID")
    status: ProcessingStatus = Field(..., description="Fetch status")
    
    # Statistics
    jobs_fetched: int = Field(ge=0, description="Number of jobs fetched")
    jobs_processed: int = Field(ge=0, description="Number of jobs processed")
    jobs_added: int = Field(ge=0, description="Number of new jobs added")
    jobs_updated: int = Field(ge=0, description="Number of existing jobs updated")
    duplicates_found: int = Field(ge=0, description="Number of duplicates found")
    errors_count: int = Field(ge=0, description="Number of errors")
    
    # Timing
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    execution_time_ms: Optional[int] = Field(None, ge=0)
    
    # Error details
    errors: List[str] = Field(default_factory=list, description="List of errors")
    warnings: List[str] = Field(default_factory=list, description="List of warnings")


class SourceStats(BaseModel):
    """Statistics for a job source."""
    
    source_id: int = Field(..., description="Source ID")
    
    # Success metrics
    success_rate: float = Field(ge=0, le=100, description="Success rate percentage")
    consecutive_failures: int = Field(ge=0, description="Consecutive failures")
    last_successful_fetch: Optional[datetime] = Field(None, description="Last successful fetch")
    
    # Volume metrics
    total_jobs_fetched: int = Field(ge=0, description="Total jobs fetched")
    total_jobs_added: int = Field(ge=0, description="Total jobs added to database")
    average_fetch_time_ms: Optional[int] = Field(None, ge=0, description="Average fetch time")
    
    # Quality metrics
    average_quality_score: Optional[float] = Field(None, ge=0, le=100)
    spam_rate: Optional[float] = Field(None, ge=0, le=100)
    duplicate_rate: Optional[float] = Field(None, ge=0, le=100)
    
    # Cost metrics
    cost_per_call: Decimal = Field(default=Decimal('0.0000'), ge=0)
    monthly_spend: Decimal = Field(default=Decimal('0.00'), ge=0)
    calls_made_today: int = Field(ge=0, description="API calls made today")


class SourceHealthCheck(BaseModel):
    """Health check result for a job source."""
    
    source_id: int = Field(..., description="Source ID")
    is_healthy: bool = Field(..., description="Whether source is healthy")
    response_time_ms: Optional[int] = Field(None, ge=0, description="Response time")
    last_check: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = Field(None, description="Error message if unhealthy")
    recommendations: List[str] = Field(default_factory=list, description="Improvement recommendations")