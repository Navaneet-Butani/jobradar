"""Pydantic models for job data processing and API operations."""

# Import all Pydantic models
from .base import (
    TimestampMixin,
    ProcessingResult,
    ValidationResult,
    DeduplicationResult,
    ProcessingStats,
)

from .common import (
    EmploymentType,
    ExperienceLevel,
    WorkArrangement,
    SalaryPeriod,
    Currency,
    JobStatus,
    ProcessingStatus,
    SkillCategory,
    ProficiencyLevel,
    CompanySize,
    AlertFrequency,
    QualityIssue,
    ApplicationStatus,
    ApplicationMethod,
    JobId,
    CompanyId,
    UserId,
    SourceId,
    SkillId,
    ApplicationId,
)

from .company import (
    CompanyInfo,
    CompanyMatch,
    CompanyNormalizationResult,
    CompanyCreate,
    CompanyUpdate,
    CompanyStats,
    CompanyEnrichment,
    CompanySearchCriteria,
)

from .source import (
    FieldMapping,
    ExtractionRules,
    SourceConfig,
    RawJobData,
    SourceFetchRequest,
    SourceFetchResult,
    SourceStats,
    SourceHealthCheck,
)

from .job import (
    LocationInfo,
    SalaryInfo,
    SkillInfo,
    JobBase,
    RawJob,
    StandardJob,
    ProcessedJob,
    JobSearchCriteria,
    JobAnalytics,
    JobRecommendation,
)

from .user import (
    UserProfile,
    UserSkill,
    JobAlert,
    SavedJob,
    CompanyWatchlist,
    UserActivity,
    UserPreferences,
    UserStats,
    UserCreate,
    UserUpdate,
    ApplicationCreate,
    ApplicationUpdate,
    ApplicationResponse,
    ApplicationStats,
)

# Keep the SQLAlchemy models separate - they stay here for database operations
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import (
    Boolean, Column, Computed, DateTime, Integer, LargeBinary, String, Text, Numeric,
    ForeignKey, UniqueConstraint, CheckConstraint, Index, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET, TSVECTOR, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from uuid import uuid4

Base = declarative_base()


class TimestampMixinDB:
    """Mixin for created_at and updated_at timestamps."""
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


# =====================================================
# LOOKUP TABLES
# =====================================================

class EmploymentTypeDB(Base):
    __tablename__ = "employment_types"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    jobs: Mapped[List["JobDB"]] = relationship("JobDB", back_populates="employment_type")


class ExperienceLevelDB(Base):
    __tablename__ = "experience_levels"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    min_years: Mapped[Optional[int]] = mapped_column(Integer)
    max_years: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    jobs: Mapped[List["JobDB"]] = relationship("JobDB", back_populates="experience_level")


class WorkArrangementDB(Base):
    __tablename__ = "work_arrangements"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    jobs: Mapped[List["JobDB"]] = relationship("JobDB", back_populates="work_arrangement")


class CompanySizeDB(Base):
    __tablename__ = "company_sizes"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    min_employees: Mapped[Optional[int]] = mapped_column(Integer)
    max_employees: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    companies: Mapped[List["CompanyDB"]] = relationship("CompanyDB", back_populates="size")


class UserDB(Base, TimestampMixinDB):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(UUID(as_uuid=False), unique=True, nullable=False, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    
    # OAuth integration
    google_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    
    # Account status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verification_token: Mapped[Optional[str]] = mapped_column(String(255))
    # Gates the deployment-wide settings (which role categories the scrapers
    # collect). Not a role system -- there are two accounts, and only one of
    # them should be able to change what the whole pipeline ingests.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    
    # Tracking
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships
    # selectin, not the default lazy load: five call sites read user.profile to
    # build a display name (registration, password reset, alerts, /auth/me), and
    # a lazy load there fires sync IO inside async and raises MissingGreenlet --
    # that is what made POST /auth/register 500 on every attempt.
    profile: Mapped[Optional["UserProfileDB"]] = relationship(
        "UserProfileDB", back_populates="user", uselist=False, lazy="selectin"
    )
    applications: Mapped[List["ApplicationDB"]] = relationship("ApplicationDB", back_populates="user")
    
    # Indexes
    __table_args__ = (
        Index('idx_users_email', 'email'),
        Index('idx_users_google_id', 'google_id'),
        Index('idx_users_active', 'is_active'),
    )


class UserProfileDB(Base, TimestampMixinDB):
    __tablename__ = "user_profiles"
    
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    experience_years: Mapped[Optional[int]] = mapped_column(Integer, CheckConstraint("experience_years >= 0"))
    resume_url: Mapped[Optional[str]] = mapped_column(String(500))
    profile_picture_url: Mapped[Optional[str]] = mapped_column(String(500))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    portfolio_url: Mapped[Optional[str]] = mapped_column(String(500))
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500))
    github_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Relationships
    user: Mapped["UserDB"] = relationship("UserDB", back_populates="profile")


class JobSourceDB(Base, TimestampMixinDB):
    __tablename__ = "job_sources"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), CheckConstraint("type IN ('api', 'scraping')"), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Status and reliability
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    success_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=100.00)
    last_successful_fetch: Mapped[Optional[datetime]] = mapped_column(DateTime)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    
    # Rate limiting and costs
    hourly_quota: Mapped[int] = mapped_column(Integer, default=100)
    daily_quota: Mapped[int] = mapped_column(Integer, default=1000)
    monthly_quota: Mapped[int] = mapped_column(Integer, default=10000)
    calls_made_today: Mapped[int] = mapped_column(Integer, default=0)
    cost_per_call: Mapped[float] = mapped_column(Numeric(8, 4), default=0.0000)
    monthly_budget: Mapped[float] = mapped_column(Numeric(10, 2), default=100.00)
    monthly_spend: Mapped[float] = mapped_column(Numeric(10, 2), default=0.00)
    
    # Configuration (JSONB fields)
    api_config: Mapped[Optional[dict]] = mapped_column(JSONB)
    scraping_config: Mapped[Optional[dict]] = mapped_column(JSONB)
    field_mapping: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    # Statistics
    total_jobs_fetched: Mapped[int] = mapped_column(Integer, default=0)
    total_jobs_added: Mapped[int] = mapped_column(Integer, default=0)
    average_fetch_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Relationships
    jobs: Mapped[List["JobDB"]] = relationship("JobDB", back_populates="source")
    fetch_logs: Mapped[List["SourceFetchLogDB"]] = relationship("SourceFetchLogDB", back_populates="source")


class CompanyDB(Base, TimestampMixinDB):
    __tablename__ = "companies"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(UUID(as_uuid=False), unique=True, nullable=False, default=lambda: str(uuid4()))
    
    # Basic information
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    website: Mapped[Optional[str]] = mapped_column(String(500))
    career_page_url: Mapped[Optional[str]] = mapped_column(String(500))
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Company details
    description: Mapped[Optional[str]] = mapped_column(Text)
    headquarters: Mapped[Optional[str]] = mapped_column(String(255))
    size_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("company_sizes.id"))
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    founded_year: Mapped[Optional[int]] = mapped_column(Integer, CheckConstraint("founded_year >= 1800 AND founded_year <= EXTRACT(YEAR FROM CURRENT_DATE)"))
    
    # Metrics
    employee_count: Mapped[Optional[int]] = mapped_column(Integer)
    glassdoor_rating: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), CheckConstraint("glassdoor_rating >= 0 AND glassdoor_rating <= 5"))
    
    # Job statistics
    total_jobs_posted: Mapped[int] = mapped_column(Integer, default=0)
    active_jobs_count: Mapped[int] = mapped_column(Integer, default=0)
    last_job_posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Verification and quality
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    data_quality_score: Mapped[float] = mapped_column(Numeric(5, 2), default=50.00)
    
    # Social media
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500))
    twitter_url: Mapped[Optional[str]] = mapped_column(String(500))
    linkedin_company_id: Mapped[Optional[str]] = mapped_column(String(100))

    # ATS (Greenhouse/Lever/Ashby) — Phase 1 Task 2
    ats_type: Mapped[Optional[str]] = mapped_column(String(20))
    ats_slug: Mapped[Optional[str]] = mapped_column(String(255))
    ats_is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ats_last_polled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ats_discovery_attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Careers-page contact discovery — Phase 3 Task 3.1. `contact_checked_at`
    # is set even when nothing was found, so a miss isn't re-fetched every packet.
    contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    contact_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Company profile mined out of job_details.raw_data — see
    # app/services/enrichment/raw_backfill.py. `rating` is whatever the source
    # publishes (AmbitionBox via Hirist), which is not the same scale as
    # glassdoor_rating above, hence its own column plus rating_source.
    rating: Mapped[Optional[float]] = mapped_column(Numeric(3, 2))
    rating_count: Mapped[Optional[int]] = mapped_column(Integer)
    rating_url: Mapped[Optional[str]] = mapped_column(String(500))
    rating_source: Mapped[Optional[str]] = mapped_column(String(50))
    employee_range: Mapped[Optional[str]] = mapped_column(String(50))
    tagline: Mapped[Optional[str]] = mapped_column(String(255))

    # Relationships
    size: Mapped[Optional["CompanySizeDB"]] = relationship("CompanySizeDB", back_populates="companies")
    jobs: Mapped[List["JobDB"]] = relationship("JobDB", back_populates="company")

    # Indexes
    __table_args__ = (
        Index('idx_companies_slug', 'slug'),
        Index('idx_companies_name', 'name'),
        Index('idx_companies_size', 'size_id'),
        Index('idx_companies_industry', 'industry'),
        Index('idx_companies_active_jobs', 'active_jobs_count'),
        Index('idx_companies_ats', 'ats_type', 'ats_slug'),
    )


class JobDB(Base, TimestampMixinDB):
    __tablename__ = "jobs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(UUID(as_uuid=False), unique=True, nullable=False, default=lambda: str(uuid4()))
    
    # Source tracking
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("job_sources.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    
    # Company relationship
    company_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("companies.id"))
    
    # Core job information
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_title: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Location details
    location_raw: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state_province: Mapped[Optional[str]] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(50), default="Unknown")
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False)
    remote_scope: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Job characteristics
    employment_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("employment_types.id"))
    experience_level_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("experience_levels.id"))
    work_arrangement_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("work_arrangements.id"))
    department: Mapped[Optional[str]] = mapped_column(String(100))
    min_exp_years: Mapped[Optional[int]] = mapped_column(Integer)
    max_exp_years: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Salary information
    salary_min: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    salary_currency: Mapped[str] = mapped_column(String(3), default="USD")
    salary_period: Mapped[str] = mapped_column(String(10), CheckConstraint("salary_period IN ('hour', 'month', 'year')"), default="year")
    salary_disclosed: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Application details
    apply_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    apply_email: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Skills (JSONB fields)
    skills_required: Mapped[list] = mapped_column(JSONB, default=list)
    skills_preferred: Mapped[list] = mapped_column(JSONB, default=list)
    skills_extracted: Mapped[list] = mapped_column(JSONB, default=list)
    
    # Dates and status
    posted_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    application_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    
    # Status tracking
    status: Mapped[str] = mapped_column(String(20), CheckConstraint("status IN ('active', 'expired', 'filled', 'invalid', 'pending_review')"), default="active")
    
    # Quality and validation
    is_valid_link: Mapped[bool] = mapped_column(Boolean, default=True)
    quality_score: Mapped[float] = mapped_column(Numeric(5, 2), default=50.00)
    spam_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0.00)
    
    # Deduplication
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    similarity_group_id: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Who posted it, where the source says so (Hirist ships a recruiter block
    # on every job; most sources ship nothing).
    poster_name: Mapped[Optional[str]] = mapped_column(String(255))
    poster_title: Mapped[Optional[str]] = mapped_column(String(255))

    # The source board's own counters — how many people already applied and
    # how many viewed it. Competition signal, not our analytics.
    source_applicant_count: Mapped[Optional[int]] = mapped_column(Integer)
    source_view_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Analytics (JobRadar's own, not the source's)
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    clicks_count: Mapped[int] = mapped_column(Integer, default=0)
    applications_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Additional metadata
    benefits: Mapped[list] = mapped_column(JSONB, default=list)
    
    # Search vector (for full-text search) — GENERATED ALWAYS in Postgres,
    # computed server-side from title/normalized_title/department.
    # Computed() tells SQLAlchemy to never include this in INSERT/UPDATE.
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('job_search', coalesce(title, '') || ' ' || "
            "coalesce(normalized_title, '') || ' ' || coalesce(department, ''))",
            persisted=True
        )
    )
    
    # Relationships
    source: Mapped["JobSourceDB"] = relationship("JobSourceDB", back_populates="jobs")
    company: Mapped[Optional["CompanyDB"]] = relationship("CompanyDB", back_populates="jobs")
    employment_type: Mapped[Optional["EmploymentTypeDB"]] = relationship("EmploymentTypeDB", back_populates="jobs")
    experience_level: Mapped[Optional["ExperienceLevelDB"]] = relationship("ExperienceLevelDB", back_populates="jobs")
    work_arrangement: Mapped[Optional["WorkArrangementDB"]] = relationship("WorkArrangementDB", back_populates="jobs")
    job_details: Mapped[Optional["JobDetailDB"]] = relationship("JobDetailDB", back_populates="job", uselist=False)
    
    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint('source_id', 'external_id'),
        Index('idx_jobs_company', 'company_id'),
        Index('idx_jobs_source', 'source_id'),
        Index('idx_jobs_status', 'status'),
        Index('idx_jobs_posted_desc', 'posted_date'),
        Index('idx_jobs_location', 'city', 'country'),
        Index('idx_jobs_remote', 'is_remote'),
        Index('idx_jobs_remote_scope', 'remote_scope'),
        Index('idx_jobs_experience', 'experience_level_id'),
        Index('idx_jobs_employment', 'employment_type_id'),
        Index('idx_jobs_content_hash', 'content_hash'),
        Index('idx_jobs_location_remote_status', 'city', 'is_remote', 'status'),
        Index('idx_jobs_search_vector', 'search_vector', postgresql_using='gin'),
        Index('idx_jobs_company_active', 'company_id', 'status'),
        Index('idx_jobs_salary_range', 'salary_min', 'salary_max'),
    )


class JobDetailDB(Base):
    __tablename__ = "job_details"
    
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    requirements: Mapped[Optional[str]] = mapped_column(Text)
    responsibilities: Mapped[Optional[str]] = mapped_column(Text)
    company_benefits: Mapped[Optional[str]] = mapped_column(Text)
    how_to_apply: Mapped[Optional[str]] = mapped_column(Text)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    contact_emails: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    
    # Search vector for job details — GENERATED ALWAYS in Postgres, computed
    # server-side from description/requirements/responsibilities.
    details_search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('job_search', coalesce(description, '') || ' ' || "
            "coalesce(requirements, '') || ' ' || coalesce(responsibilities, ''))",
            persisted=True
        )
    )
    
    # Relationships
    job: Mapped["JobDB"] = relationship("JobDB", back_populates="job_details")

    __table_args__ = (
        Index('idx_job_details_search_vector', 'details_search_vector', postgresql_using='gin'),
    )


class ApplicationDB(Base, TimestampMixinDB):
    """Database model for tracking user job applications."""
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"))
    job_profile_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("job_profiles.id", ondelete="SET NULL"))

    # Application details — pipeline: applied -> screening -> interview -> offer, or rejected/ghosted
    status: Mapped[str] = mapped_column(String(30),
        CheckConstraint("status IN ('applied', 'screening', 'interview', 'offer', 'rejected', 'ghosted')"),
        default="applied")
    applied_date: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    application_method: Mapped[str] = mapped_column(String(20),
        CheckConstraint("application_method IN ('direct', 'portal', 'email', 'referral', 'ats_form')"),
        default="direct")

    # Application materials
    resume_version: Mapped[Optional[str]] = mapped_column(String(100))
    cover_letter: Mapped[bool] = mapped_column(Boolean, default=False)
    referral_name: Mapped[Optional[str]] = mapped_column(String(100))

    # Contact discovered for this application (Phase 3 Task 3.1)
    contact_name: Mapped[Optional[str]] = mapped_column(String(100))
    contact_email: Mapped[Optional[str]] = mapped_column(String(255))

    # Tracking and notes
    notes: Mapped[Optional[str]] = mapped_column(Text)
    next_step: Mapped[Optional[str]] = mapped_column(String(255))
    next_step_date: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Append-only log of status transitions: [{at, from_status, to_status, note}]
    timeline: Mapped[list] = mapped_column(JSONB, default=list, server_default='[]')

    # Response tracking
    response_received: Mapped[bool] = mapped_column(Boolean, default=False)
    response_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    interview_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    user: Mapped["UserDB"] = relationship("UserDB")
    job: Mapped["JobDB"] = relationship("JobDB")

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint('user_id', 'job_id', name='unique_user_job_application'),
        Index('idx_applications_user_id', 'user_id'),
        Index('idx_applications_status', 'status'),
        Index('idx_applications_applied_date', 'applied_date'),
        Index('idx_applications_user_status', 'user_id', 'status'),
        Index('idx_applications_next_step_date', 'next_step_date'),
        Index('idx_applications_job_profile_id', 'job_profile_id'),
    )


# =====================================================
# SKILLS AND SUBSCRIPTION TABLES
# =====================================================

class SourceFetchLogDB(Base):
    __tablename__ = "source_fetch_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("job_sources.id"))
    batch_uuid: Mapped[str] = mapped_column(UUID(as_uuid=False), default=lambda: str(uuid4()))
    
    status: Mapped[str] = mapped_column(String(20), CheckConstraint("status IN ('running', 'completed', 'failed')"), default="running")
    jobs_fetched: Mapped[int] = mapped_column(Integer, default=0)
    jobs_processed: Mapped[int] = mapped_column(Integer, default=0)
    jobs_added: Mapped[int] = mapped_column(Integer, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_details: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    # Relationships
    source: Mapped[Optional["JobSourceDB"]] = relationship("JobSourceDB", back_populates="fetch_logs")
    
    # Indexes
    __table_args__ = (
        Index('idx_fetch_logs_source_status', 'source_id', 'status'),
        Index('idx_fetch_logs_started', 'started_at'),
    )


class SystemSettingDB(Base):
    __tablename__ = "system_settings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(20), CheckConstraint("value_type IN ('string', 'integer', 'boolean', 'json')"), default="string")
    description: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class UserSessionDB(Base, TimestampMixinDB):
    """Database model for user session management and tracking."""
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Token management
    refresh_token: Mapped[Optional[str]] = mapped_column(String(500))
    refresh_token_expires: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Device and location tracking
    device_info: Mapped[Optional[dict]] = mapped_column(JSONB)
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    # Session status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    user: Mapped["UserDB"] = relationship("UserDB")

    # Indexes
    __table_args__ = (
        Index('idx_user_sessions_session_id', 'session_id'),
        Index('idx_user_sessions_user_id', 'user_id'),
        Index('idx_user_sessions_active', 'is_active', 'expires_at'),
        Index('idx_user_sessions_refresh_token', 'refresh_token'),
        Index('idx_user_sessions_ip', 'ip_address'),
    )


class PasswordResetTokenDB(Base):
    """Database model for password reset tokens."""
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Token status
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Security tracking
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    user: Mapped["UserDB"] = relationship("UserDB")

    # Indexes
    __table_args__ = (
        Index('idx_password_reset_token', 'token'),
        Index('idx_password_reset_user_id', 'user_id'),
        Index('idx_password_reset_expires', 'expires_at'),
        Index('idx_password_reset_unused', 'is_used', 'expires_at'),
    )


class EmailVerificationTokenDB(Base):
    """Database model for email verification tokens."""
    __tablename__ = "email_verification_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Token status
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Tracking
    verification_attempts: Mapped[int] = mapped_column(Integer, default=0)
    ip_address: Mapped[Optional[str]] = mapped_column(INET)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    user: Mapped["UserDB"] = relationship("UserDB")

    # Indexes
    __table_args__ = (
        Index('idx_email_verification_token', 'token'),
        Index('idx_email_verification_user_id', 'user_id'),
        Index('idx_email_verification_email', 'email'),
        Index('idx_email_verification_expires', 'expires_at'),
        Index('idx_email_verification_unverified', 'is_verified', 'expires_at'),
    )


class SecurityAuditLogDB(Base):
    """Database model for security audit logging."""
    __tablename__ = "security_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    # Event details
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_category: Mapped[str] = mapped_column(String(30), CheckConstraint("event_category IN ('authentication', 'authorization', 'account', 'security', 'system')"), nullable=False)
    event_description: Mapped[str] = mapped_column(Text, nullable=False)

    # Request details
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    request_path: Mapped[Optional[str]] = mapped_column(String(500))
    request_method: Mapped[Optional[str]] = mapped_column(String(10))

    # Event metadata
    event_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    severity: Mapped[str] = mapped_column(String(10), CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')"), default='medium')

    # Success/failure tracking
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    user: Mapped[Optional["UserDB"]] = relationship("UserDB")

    # Indexes
    __table_args__ = (
        Index('idx_security_audit_user_id', 'user_id'),
        Index('idx_security_audit_event_type', 'event_type'),
        Index('idx_security_audit_category', 'event_category'),
        Index('idx_security_audit_created', 'created_at'),
        Index('idx_security_audit_ip', 'ip_address'),
        Index('idx_security_audit_severity', 'severity'),
        Index('idx_security_audit_success', 'success'),
        Index('idx_security_audit_user_events', 'user_id', 'event_type', 'created_at'),
    )


class RevokedTokenDB(Base):
    """Database model for tracking revoked JWT tokens."""
    __tablename__ = "revoked_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jti: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)  # JWT ID
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    # Token details
    token_type: Mapped[str] = mapped_column(String(20), CheckConstraint("token_type IN ('access', 'refresh')"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Revocation details
    revoked_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    revoked_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    revocation_reason: Mapped[Optional[str]] = mapped_column(String(100))

    # Relationships
    user: Mapped[Optional["UserDB"]] = relationship("UserDB", foreign_keys=[user_id])
    revoked_by_user: Mapped[Optional["UserDB"]] = relationship("UserDB", foreign_keys=[revoked_by])

    # Indexes
    __table_args__ = (
        Index('idx_revoked_tokens_jti', 'jti'),
        Index('idx_revoked_tokens_user_id', 'user_id'),
        Index('idx_revoked_tokens_expires', 'expires_at'),
        Index('idx_revoked_tokens_type', 'token_type'),
    )


# === DEDUPLICATION SYSTEM DATABASE MODELS === #

class DuplicateGroupDB(Base):
    """Database model for duplicate job groups with performance optimization."""
    __tablename__ = "duplicate_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    primary_job_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"))
    group_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    quality_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    primary_job: Mapped[Optional["JobDB"]] = relationship("JobDB", foreign_keys=[primary_job_id])
    members: Mapped[List["DuplicateMappingDB"]] = relationship("DuplicateMappingDB", back_populates="group", cascade="all, delete-orphan")

    # Performance indexes
    __table_args__ = (
        Index('idx_duplicate_groups_primary_job', 'primary_job_id'),
        Index('idx_duplicate_groups_hash', 'group_hash'),
        Index('idx_duplicate_groups_quality_desc', 'quality_score'),
        Index('idx_duplicate_groups_updated_desc', 'updated_at'),
        Index('idx_duplicate_groups_member_count', 'member_count'),
    )


class DuplicateMappingDB(Base):
    """Database model for job-to-group mappings with deduplication metadata."""
    __tablename__ = "duplicate_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), unique=True, nullable=False)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("duplicate_groups.id", ondelete="CASCADE"), nullable=False)
    similarity_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    merge_status: Mapped[str] = mapped_column(String(20), CheckConstraint("merge_status IN ('pending', 'completed', 'failed', 'skipped')"), default='pending')
    match_factors: Mapped[Optional[dict]] = mapped_column(JSONB)  # Detailed similarity analysis
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    job: Mapped["JobDB"] = relationship("JobDB")
    group: Mapped["DuplicateGroupDB"] = relationship("DuplicateGroupDB", back_populates="members")

    # Performance indexes
    __table_args__ = (
        Index('idx_duplicate_mappings_job_id', 'job_id'),
        Index('idx_duplicate_mappings_group_id', 'group_id'),
        Index('idx_duplicate_mappings_primary_only', 'is_primary'),
        Index('idx_duplicate_mappings_similarity_desc', 'similarity_score'),
        Index('idx_duplicate_mappings_status', 'merge_status'),
        Index('idx_duplicate_mappings_group_similarity', 'group_id', 'similarity_score'),
    )


class JobProfileDB(Base, TimestampMixinDB):
    """A named search profile — a user may run several (Phase 2)."""
    __tablename__ = "job_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(UUID(as_uuid=False), unique=True, nullable=False, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    years_exp: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)
    seniority_floor: Mapped[Optional[str]] = mapped_column(String(20))
    seniority_ceiling: Mapped[Optional[str]] = mapped_column(String(20))

    must_have_skills: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)
    nice_to_have_skills: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)
    target_titles: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)

    cities: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)
    metro_cities: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)
    accepts_remote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remote_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remote_scope: Mapped[str] = mapped_column(String(20), nullable=False, default='india_only')

    min_salary_inr: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    exclude_companies: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)
    exclude_keywords: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)
    include_staffing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Small score bonus when a posting mentions one of these (e.g. fintech, healthcare)
    domain_keywords: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)
    # Penalise "CS degree mandatory" postings for people without one
    no_cs_degree: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Telegram / Discord / Slack / ntfy webhook for new-match alerts (app/services/notify.py)
    notify_webhook_url: Mapped[Optional[str]] = mapped_column(Text)

    # Standard-answer prefills for the application packet (Phase 3 Task 3)
    notice_period_days: Mapped[Optional[int]] = mapped_column(Integer)
    current_ctc_inr: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    expected_ctc_inr: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    willing_to_relocate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    user: Mapped["UserDB"] = relationship("UserDB")
    matches: Mapped[List["MatchDB"]] = relationship("MatchDB", back_populates="job_profile", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_job_profiles_user_id', 'user_id'),
        Index('idx_job_profiles_is_active', 'is_active'),
    )


class MatchDB(Base):
    """A scored (job_profile, job) pair — the ranked feed's backing table."""
    __tablename__ = "matches"

    job_profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("job_profiles.id", ondelete="CASCADE"), primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    reasons: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    state: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("state IN ('new', 'seen', 'interested', 'applied', 'dismissed')"),
        nullable=False,
        default='new',
    )
    surfaced_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)  # pushed to the profile's webhook
    state_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    job_profile: Mapped["JobProfileDB"] = relationship("JobProfileDB", back_populates="matches")
    job: Mapped["JobDB"] = relationship("JobDB")

    __table_args__ = (
        Index('idx_matches_feed', 'job_profile_id', 'state', 'score'),
    )


class UserResumeDB(Base, TimestampMixinDB):
    """The user's master resume — extracted text only, one per user (Phase 3 Task 3).

    The original file is deliberately not kept: the text is all the packet
    generator needs, and storing binaries eats the 500 MB Supabase budget.
    Re-uploading replaces the row.
    """
    __tablename__ = "user_resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(100))
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Original bytes, kept only so outreach emails can attach the real file.
    file_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    file_size: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    user: Mapped["UserDB"] = relationship("UserDB")

    __table_args__ = (
        UniqueConstraint('user_id', name='unique_user_resume'),
    )


# =====================================================
# OUTREACH TABLES (Phase 3 Task 3 extension)
# =====================================================

class UserEmailAccountDB(Base, TimestampMixinDB):
    """A user's own SMTP send identity.

    Outreach must never go out from a shared address — replies and spam
    reputation both belong to the person, not the app. The password is a
    Gmail app password, stored Fernet-encrypted (see
    `app/services/outreach/crypto.py`); it is never returned by the API.
    """
    __tablename__ = "user_email_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    from_name: Mapped[str] = mapped_column(String(120), nullable=False)
    from_email: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False, default="smtp.gmail.com")
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_username: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    daily_send_cap: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    send_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    signature: Mapped[Optional[str]] = mapped_column(Text)

    # Replies and bounces are read back from the same mailbox over IMAP.
    imap_host: Mapped[str] = mapped_column(String(255), nullable=False, default="imap.gmail.com")
    imap_port: Mapped[int] = mapped_column(Integer, nullable=False, default=993)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text)

    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    user: Mapped["UserDB"] = relationship("UserDB")

    __table_args__ = (
        UniqueConstraint('user_id', name='unique_user_email_account'),
    )


class OutreachContactDB(Base, TimestampMixinDB):
    """A known HR/hiring contact — typed in by hand or imported from CSV."""
    __tablename__ = "outreach_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[Optional[str]] = mapped_column(String(150))
    company_name: Mapped[Optional[str]] = mapped_column(String(255))
    title: Mapped[Optional[str]] = mapped_column(String(150))
    role_hint: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")

    user: Mapped["UserDB"] = relationship("UserDB")

    __table_args__ = (
        UniqueConstraint('user_id', 'email', name='unique_user_contact_email'),
        Index('idx_outreach_contacts_user', 'user_id'),
    )


class OutreachCampaignDB(Base, TimestampMixinDB):
    """A batch send over selected contacts, paced against the user's daily cap."""
    __tablename__ = "outreach_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    subject_template: Mapped[str] = mapped_column(Text, nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("status IN ('draft', 'running', 'paused', 'completed')", name="ck_outreach_campaigns_status"),
        nullable=False,
        default="draft",
    )
    attach_resume: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    personalize_with_llm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Sequence: one follow-up, only to people who neither replied nor bounced.
    followup_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    followup_after_days: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    followup_subject_template: Mapped[Optional[str]] = mapped_column(Text)
    followup_body_template: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped["UserDB"] = relationship("UserDB")
    messages: Mapped[List["OutreachMessageDB"]] = relationship(
        "OutreachMessageDB", back_populates="campaign", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('idx_outreach_campaigns_user', 'user_id'),
    )


class OutreachMessageDB(Base, TimestampMixinDB):
    """One outbound email — from a campaign or from a single application.

    Both send paths write here, so this table is the whole outreach history
    and the thing the per-day cap counts against.
    """
    __tablename__ = "outreach_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("outreach_campaigns.id", ondelete="CASCADE"))
    contact_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("outreach_contacts.id", ondelete="SET NULL"))
    application_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("applications.id", ondelete="SET NULL"))

    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    to_name: Mapped[Optional[str]] = mapped_column(String(150))
    company_name: Mapped[Optional[str]] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attached_resume: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "status IN ('queued', 'sent', 'failed', 'skipped', 'cancelled')",
            name="ck_outreach_messages_status",
        ),
        nullable=False,
        default="queued",
    )
    error: Mapped[Optional[str]] = mapped_column(Text)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # The RFC Message-ID we stamped on the outgoing mail. Everything downstream
    # (reply matching, bounce matching, threading the follow-up) hangs off this.
    message_id: Mapped[Optional[str]] = mapped_column(String(255))

    # Sequence position: 1 = the initial email, 2 = the follow-up.
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("outreach_messages.id", ondelete="CASCADE"))
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Feedback read back from the mailbox — never guessed from a send succeeding.
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reply_from: Mapped[Optional[str]] = mapped_column(String(255))
    reply_snippet: Mapped[Optional[str]] = mapped_column(Text)
    bounced_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    bounce_reason: Mapped[Optional[str]] = mapped_column(Text)

    campaign: Mapped[Optional["OutreachCampaignDB"]] = relationship("OutreachCampaignDB", back_populates="messages")
    parent: Mapped[Optional["OutreachMessageDB"]] = relationship("OutreachMessageDB", remote_side=[id])

    __table_args__ = (
        Index('idx_outreach_messages_user_sent', 'user_id', 'sent_at'),
        Index('idx_outreach_messages_campaign', 'campaign_id', 'status'),
        Index('idx_outreach_messages_to_email', 'user_id', 'to_email'),
        Index('idx_outreach_messages_message_id', 'message_id'),
        Index('idx_outreach_messages_followup', 'campaign_id', 'step', 'status', 'replied_at'),
    )


# Export all for easy access
__all__ = [
    # Pydantic models
    "TimestampMixin", "ProcessingResult", "ValidationResult", "DeduplicationResult", "ProcessingStats",
    "EmploymentType", "ExperienceLevel", "WorkArrangement", "SalaryPeriod", "Currency", "JobStatus",
    "ProcessingStatus", "SkillCategory", "ProficiencyLevel", "CompanySize", "AlertFrequency", "QualityIssue",
    "ApplicationStatus", "ApplicationMethod", "JobId", "CompanyId", "UserId", "SourceId", "SkillId", "ApplicationId",
    "CompanyInfo", "CompanyMatch", "CompanyNormalizationResult", "CompanyCreate", "CompanyUpdate", 
    "CompanyStats", "CompanyEnrichment", "CompanySearchCriteria",
    "FieldMapping", "ExtractionRules", "SourceConfig", "RawJobData", "SourceFetchRequest", 
    "SourceFetchResult", "SourceStats", "SourceHealthCheck",
    "LocationInfo", "SalaryInfo", "SkillInfo", "JobBase", "RawJob", "StandardJob", "ProcessedJob",
    "JobSearchCriteria", "JobAnalytics", "JobRecommendation",
    "UserProfile", "UserSkill", "JobAlert", "SavedJob", "CompanyWatchlist", "UserActivity",
    "UserPreferences", "UserStats", "UserCreate", "UserUpdate",
    "ApplicationCreate", "ApplicationUpdate", "ApplicationResponse", "ApplicationStats",
    
    # SQLAlchemy models
    "Base", "TimestampMixinDB",
    "EmploymentTypeDB", "ExperienceLevelDB", "WorkArrangementDB", "CompanySizeDB",
    "UserDB", "UserProfileDB", "JobSourceDB", "CompanyDB", "JobDB", "JobDetailDB",
    "ApplicationDB",
    "SourceFetchLogDB", "SystemSettingDB",
    # Authentication models
    "UserSessionDB", "PasswordResetTokenDB", "EmailVerificationTokenDB", "SecurityAuditLogDB", "RevokedTokenDB",
    # Deduplication models
    "DuplicateGroupDB", "DuplicateMappingDB",
    # Matching models (Phase 2)
    "JobProfileDB", "MatchDB",
    # Application packet models (Phase 3 Task 3)
    "UserResumeDB",
    # Outreach models (Phase 3 Task 3 extension)
    "UserEmailAccountDB", "OutreachContactDB", "OutreachCampaignDB", "OutreachMessageDB"
]
