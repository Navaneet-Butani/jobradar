"""Pydantic models for the profiles API."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class JobProfileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    years_exp: float = Field(..., ge=0, le=50)
    seniority_floor: Optional[str] = None
    seniority_ceiling: Optional[str] = None
    must_have_skills: List[str] = Field(default_factory=list)
    nice_to_have_skills: List[str] = Field(default_factory=list)
    target_titles: List[str] = Field(default_factory=list)
    cities: List[str] = Field(default_factory=list)
    metro_cities: List[str] = Field(default_factory=list)
    accepts_remote: bool = True
    remote_only: bool = False
    remote_scope: str = "india_only"
    min_salary_inr: Optional[float] = Field(None, ge=0)
    exclude_companies: List[str] = Field(default_factory=list)
    exclude_keywords: List[str] = Field(default_factory=list)
    include_staffing: bool = False
    domain_keywords: List[str] = Field(default_factory=list)
    no_cs_degree: bool = False
    notice_period_days: Optional[int] = Field(None, ge=0, le=365)
    current_ctc_inr: Optional[float] = Field(None, ge=0)
    expected_ctc_inr: Optional[float] = Field(None, ge=0)
    willing_to_relocate: bool = False


class JobProfileUpdateRequest(BaseModel):
    """All fields optional — PATCH applies only what's provided."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    years_exp: Optional[float] = Field(None, ge=0, le=50)
    seniority_floor: Optional[str] = None
    seniority_ceiling: Optional[str] = None
    must_have_skills: Optional[List[str]] = None
    nice_to_have_skills: Optional[List[str]] = None
    target_titles: Optional[List[str]] = None
    cities: Optional[List[str]] = None
    metro_cities: Optional[List[str]] = None
    accepts_remote: Optional[bool] = None
    remote_only: Optional[bool] = None
    remote_scope: Optional[str] = None
    min_salary_inr: Optional[float] = Field(None, ge=0)
    exclude_companies: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    include_staffing: Optional[bool] = None
    domain_keywords: Optional[List[str]] = None
    no_cs_degree: Optional[bool] = None
    notice_period_days: Optional[int] = Field(None, ge=0, le=365)
    current_ctc_inr: Optional[float] = Field(None, ge=0)
    expected_ctc_inr: Optional[float] = Field(None, ge=0)
    willing_to_relocate: Optional[bool] = None
    is_active: Optional[bool] = None


class JobProfileResponse(BaseModel):
    id: int
    uuid: str
    name: str
    years_exp: float
    seniority_floor: Optional[str]
    seniority_ceiling: Optional[str]
    must_have_skills: List[str]
    nice_to_have_skills: List[str]
    target_titles: List[str]
    cities: List[str]
    metro_cities: List[str]
    accepts_remote: bool
    remote_only: bool
    remote_scope: str
    min_salary_inr: Optional[float]
    exclude_companies: List[str]
    exclude_keywords: List[str]
    include_staffing: bool
    domain_keywords: List[str]
    no_cs_degree: bool
    notice_period_days: Optional[int]
    current_ctc_inr: Optional[float]
    expected_ctc_inr: Optional[float]
    willing_to_relocate: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
