"""User-related data models."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, EmailStr, HttpUrl

from .base import TimestampMixin
from .common import ProficiencyLevel, AlertFrequency, JobId, CompanyId, ApplicationStatus, ApplicationMethod, ApplicationId


class UserProfile(BaseModel):
    """User profile information."""
    
    first_name: Optional[str] = Field(None, max_length=100, description="First name")
    last_name: Optional[str] = Field(None, max_length=100, description="Last name")
    location: Optional[str] = Field(None, max_length=255, description="User location")
    experience_years: Optional[int] = Field(None, ge=0, description="Years of experience")
    resume_url: Optional[HttpUrl] = Field(None, description="Resume URL")
    profile_picture_url: Optional[HttpUrl] = Field(None, description="Profile picture URL")
    bio: Optional[str] = Field(None, description="User bio")
    portfolio_url: Optional[HttpUrl] = Field(None, description="Portfolio URL")
    linkedin_url: Optional[HttpUrl] = Field(None, description="LinkedIn profile URL")
    github_url: Optional[HttpUrl] = Field(None, description="GitHub profile URL")


class UserSkill(BaseModel):
    """User skill with proficiency level."""
    
    skill_id: int = Field(..., description="Skill ID")
    skill_name: str = Field(..., description="Skill name")
    proficiency_level: ProficiencyLevel = Field(default=ProficiencyLevel.INTERMEDIATE, description="Proficiency level")
    years_experience: Optional[float] = Field(None, ge=0, description="Years of experience with skill")
    is_primary: bool = Field(default=False, description="Whether this is a primary skill")


class JobAlert(BaseModel):
    """Job alert configuration."""
    
    id: Optional[int] = Field(None, description="Alert ID")
    user_id: int = Field(..., description="User ID")
    name: str = Field(..., max_length=255, description="Alert name")
    query_params: dict = Field(..., description="Search parameters")
    frequency: AlertFrequency = Field(default=AlertFrequency.DAILY, description="Alert frequency")
    email_enabled: bool = Field(default=True, description="Email notifications enabled")
    slack_webhook_url: Optional[HttpUrl] = Field(None, description="Slack webhook URL")
    is_active: bool = Field(default=True, description="Whether alert is active")
    last_triggered_at: Optional[datetime] = Field(None, description="Last time alert was triggered")
    jobs_sent_count: int = Field(default=0, ge=0, description="Total jobs sent for this alert")


class SavedJob(BaseModel):
    """Saved job information."""
    
    id: Optional[int] = Field(None, description="Saved job ID")
    user_id: int = Field(..., description="User ID")
    job_id: JobId = Field(..., description="Job ID")
    notes: Optional[str] = Field(None, description="User notes about the job")
    folder: str = Field(default="default", max_length=100, description="Folder name")
    created_at: Optional[datetime] = Field(None, description="When job was saved")


class CompanyWatchlist(BaseModel):
    """Company watchlist entry."""
    
    id: Optional[int] = Field(None, description="Watchlist entry ID")
    user_id: int = Field(..., description="User ID")
    company_id: CompanyId = Field(..., description="Company ID")
    company_name: Optional[str] = Field(None, description="Company name")
    notification_enabled: bool = Field(default=True, description="Notifications enabled")
    created_at: Optional[datetime] = Field(None, description="When company was added to watchlist")


class UserActivity(BaseModel):
    """User activity tracking."""
    
    id: Optional[int] = Field(None, description="Activity ID")
    user_id: int = Field(..., description="User ID")
    activity_type: str = Field(..., max_length=50, description="Type of activity")
    job_id: Optional[JobId] = Field(None, description="Related job ID")
    details: Optional[dict] = Field(None, description="Activity details")
    ip_address: Optional[str] = Field(None, description="User IP address")
    created_at: Optional[datetime] = Field(None, description="Activity timestamp")


class UserPreferences(BaseModel):
    """User preferences and settings."""
    
    # Job preferences
    preferred_locations: List[str] = Field(default_factory=list, description="Preferred job locations")
    preferred_remote: Optional[bool] = Field(None, description="Remote work preference")
    preferred_salary_min: Optional[int] = Field(None, ge=0, description="Minimum preferred salary")
    preferred_salary_currency: str = Field(default="USD", description="Preferred currency")
    
    # Notification preferences
    email_notifications: bool = Field(default=True, description="Email notifications enabled")
    marketing_emails: bool = Field(default=False, description="Marketing emails enabled")
    job_alert_digest: bool = Field(default=True, description="Job alert digest enabled")
    
    # Privacy preferences
    profile_visibility: str = Field(default="private", description="Profile visibility")
    show_salary_expectations: bool = Field(default=False, description="Show salary expectations")
    
    # Display preferences
    jobs_per_page: int = Field(default=20, ge=10, le=100, description="Jobs per page")
    default_search_radius: int = Field(default=25, ge=0, le=100, description="Default search radius in miles")


class UserStats(BaseModel):
    """User activity statistics."""
    
    user_id: int = Field(..., description="User ID")
    
    # Job interaction stats
    total_job_views: int = Field(ge=0, description="Total job views")
    total_job_clicks: int = Field(ge=0, description="Total job clicks")
    total_applications: int = Field(ge=0, description="Total applications")
    
    # Saved jobs stats
    total_saved_jobs: int = Field(ge=0, description="Total saved jobs")
    saved_jobs_by_folder: dict = Field(default_factory=dict, description="Saved jobs grouped by folder")
    
    # Alert stats
    total_active_alerts: int = Field(ge=0, description="Number of active alerts")
    total_jobs_received: int = Field(ge=0, description="Total jobs received via alerts")
    
    # Engagement stats
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")
    days_active: int = Field(ge=0, description="Total days active")
    avg_session_duration: Optional[float] = Field(None, ge=0, description="Average session duration in minutes")
    
    # Profile completeness
    profile_completeness: float = Field(ge=0, le=100, description="Profile completeness percentage")
    missing_profile_fields: List[str] = Field(default_factory=list, description="Missing profile fields")


class UserCreate(BaseModel):
    """Model for creating new users."""
    
    email: EmailStr = Field(..., description="User email address")
    password: Optional[str] = Field(None, min_length=8, description="User password")
    google_id: Optional[str] = Field(None, description="Google OAuth ID")
    profile: Optional[UserProfile] = Field(None, description="User profile information")
    
    
class UserUpdate(BaseModel):
    """Model for updating user information."""

    email: Optional[EmailStr] = Field(None, description="User email address")
    is_active: Optional[bool] = Field(None, description="Whether user is active")
    email_verified: Optional[bool] = Field(None, description="Whether email is verified")
    profile: Optional[UserProfile] = Field(None, description="User profile information")
    preferences: Optional[UserPreferences] = Field(None, description="User preferences")


# ===========================================
# APPLICATION TRACKING MODELS
# ===========================================

class ApplicationCreate(BaseModel):
    """Model for creating new application."""
    job_id: JobId = Field(..., description="Job ID")
    job_profile_id: Optional[int] = Field(None, description="job_profiles id this application was matched under")
    status: ApplicationStatus = Field(default=ApplicationStatus.APPLIED, description="Application status")
    application_method: ApplicationMethod = Field(default=ApplicationMethod.DIRECT, description="How application was submitted")
    resume_version: Optional[str] = Field(None, max_length=100, description="Resume version used")
    cover_letter: bool = Field(default=False, description="Whether cover letter was included")
    referral_name: Optional[str] = Field(None, max_length=100, description="Referral contact name")
    contact_name: Optional[str] = Field(None, max_length=100, description="Discovered contact name")
    contact_email: Optional[str] = Field(None, max_length=255, description="Discovered contact email")
    notes: Optional[str] = Field(None, description="Application notes")
    next_step: Optional[str] = Field(None, max_length=255, description="Next step description")
    next_step_date: Optional[datetime] = Field(None, description="Next step date")


class ApplicationUpdate(BaseModel):
    """Model for updating application."""
    status: Optional[ApplicationStatus] = Field(None, description="Application status")
    notes: Optional[str] = Field(None, description="Application notes")
    next_step: Optional[str] = Field(None, max_length=255, description="Next step description")
    next_step_date: Optional[datetime] = Field(None, description="Next step date")
    contact_name: Optional[str] = Field(None, max_length=100, description="Discovered contact name")
    contact_email: Optional[str] = Field(None, max_length=255, description="Discovered contact email")
    response_received: Optional[bool] = Field(None, description="Whether response was received")
    response_date: Optional[datetime] = Field(None, description="Response date")
    interview_scheduled: Optional[bool] = Field(None, description="Whether interview is scheduled")


class ApplicationResponse(BaseModel):
    """Application response model."""
    id: ApplicationId = Field(..., description="Application ID")
    job_id: JobId = Field(..., description="Job ID")
    job_profile_id: Optional[int] = Field(None, description="job_profiles id this application was matched under")
    job_title: str = Field(..., description="Job title")
    company_name: str = Field(..., description="Company name")
    status: ApplicationStatus = Field(..., description="Application status")
    applied_date: datetime = Field(..., description="Application date")
    application_method: ApplicationMethod = Field(..., description="Application method")
    resume_version: Optional[str] = Field(None, description="Resume version")
    cover_letter: bool = Field(..., description="Cover letter included")
    referral_name: Optional[str] = Field(None, description="Referral name")
    contact_name: Optional[str] = Field(None, description="Discovered contact name")
    contact_email: Optional[str] = Field(None, description="Discovered contact email")
    notes: Optional[str] = Field(None, description="Notes")
    next_step: Optional[str] = Field(None, description="Next step")
    next_step_date: Optional[datetime] = Field(None, description="Next step date")
    timeline: List[Dict[str, Any]] = Field(default_factory=list, description="Status transition log")
    response_received: bool = Field(..., description="Response received")
    response_date: Optional[datetime] = Field(None, description="Response date")
    interview_scheduled: bool = Field(..., description="Interview scheduled")
    created_at: datetime = Field(..., description="Created timestamp")
    updated_at: datetime = Field(..., description="Updated timestamp")

    class Config:
        from_attributes = True


class ApplicationStats(BaseModel):
    """Application statistics model."""
    total_applications: int = Field(ge=0, description="Total applications")
    applications_by_status: Dict[str, int] = Field(default_factory=dict, description="Applications grouped by status")
    applications_by_method: Dict[str, int] = Field(default_factory=dict, description="Applications grouped by method")
    response_rate: float = Field(ge=0, le=100, description="Response rate percentage")
    interview_rate: float = Field(ge=0, le=100, description="Interview rate percentage")
    offer_rate: float = Field(ge=0, le=100, description="Offer rate percentage")
    avg_response_time_days: Optional[float] = Field(None, ge=0, description="Average response time in days")
    applications_this_week: int = Field(ge=0, description="Applications this week")
    applications_this_month: int = Field(ge=0, description="Applications this month")
    top_companies: List[Dict[str, Any]] = Field(default_factory=list, description="Top companies applied to")