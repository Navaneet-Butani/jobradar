"""Application tracking API schemas."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from ...models.common import ApplicationStatus, ApplicationMethod
from ...models.user import ApplicationCreate, ApplicationUpdate, ApplicationResponse, ApplicationStats


class CreateApplicationRequest(ApplicationCreate):
    """Request to create new application tracking."""
    pass


class UpdateApplicationRequest(ApplicationUpdate):
    """Request to update application."""
    pass


class ApplicationListResponse(BaseModel):
    """List of applications with pagination."""
    applications: List[ApplicationResponse] = Field(..., description="List of applications")
    total_count: int = Field(..., ge=0, description="Total number of applications")
    limit: int = Field(..., ge=1, description="Page size")
    offset: int = Field(..., ge=0, description="Page offset")


class ApplicationStatsResponse(ApplicationStats):
    """Application statistics response."""
    pass


class DueTodayResponse(BaseModel):
    """Applications with a follow-up due today or earlier."""
    applications: List[ApplicationResponse] = Field(..., description="Applications due today")
    total_count: int = Field(..., ge=0, description="Total due")


class FollowUpApplicationsResponse(BaseModel):
    """Applications needing follow-up."""
    applications: List[ApplicationResponse] = Field(..., description="Applications needing follow-up")
    total_count: int = Field(..., ge=0, description="Total follow-up applications")


class ApplicationTimelineResponse(BaseModel):
    """Application timeline data."""
    timeline: Dict[str, List[Dict[str, Any]]] = Field(..., description="Timeline data by month")
    total_months: int = Field(..., ge=0, description="Number of months with data")


class StatusUpdateRequest(BaseModel):
    """Request to update application status."""
    status: ApplicationStatus = Field(..., description="New application status")
    notes: Optional[str] = Field(None, description="Additional notes")
    response_received: Optional[bool] = Field(None, description="Whether response was received")
    response_date: Optional[datetime] = Field(None, description="Response date")
    interview_scheduled: Optional[bool] = Field(None, description="Whether interview is scheduled")
    next_step: Optional[str] = Field(None, max_length=255, description="Next step description")
    next_step_date: Optional[datetime] = Field(None, description="Next step date")


class ApplicationSummaryResponse(BaseModel):
    """Application summary for dashboard."""
    total_applications: int = Field(..., ge=0, description="Total applications")
    active_applications: int = Field(..., ge=0, description="Active applications")
    applications_this_week: int = Field(..., ge=0, description="Applications this week")
    applications_this_month: int = Field(..., ge=0, description="Applications this month")
    response_rate: float = Field(..., ge=0, le=100, description="Response rate percentage")
    interview_rate: float = Field(..., ge=0, le=100, description="Interview rate percentage")
    offer_rate: float = Field(..., ge=0, le=100, description="Offer rate percentage")
    recent_applications: List[Dict[str, Any]] = Field(..., description="Recent applications")
    follow_up_needed: int = Field(..., ge=0, description="Applications needing follow-up")


class ApplicationFilterRequest(BaseModel):
    """Request to filter applications."""
    status: Optional[List[ApplicationStatus]] = Field(None, description="Filter by status")
    application_method: Optional[List[ApplicationMethod]] = Field(None, description="Filter by method")
    company_name: Optional[str] = Field(None, description="Filter by company name")
    date_from: Optional[datetime] = Field(None, description="Applications from date")
    date_to: Optional[datetime] = Field(None, description="Applications to date")
    has_response: Optional[bool] = Field(None, description="Filter by response received")
    has_interview: Optional[bool] = Field(None, description="Filter by interview scheduled")


class ApplicationNotesUpdateRequest(BaseModel):
    """Request to update application notes."""
    notes: str = Field(..., max_length=2000, description="Updated notes")


class ApplicationDeleteResponse(BaseModel):
    """Application deletion response."""
    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Success/error message")