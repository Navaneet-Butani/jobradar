"""Pydantic models for the matches API."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

MATCH_STATES = ("new", "seen", "interested", "applied", "dismissed")


class MatchStateUpdateRequest(BaseModel):
    profile_id: int
    state: str = Field(..., pattern="^(new|seen|interested|applied|dismissed)$")


class MatchJobResponse(BaseModel):
    job_id: int
    title: str
    company_name: Optional[str]
    # Company identity, so a feed card can show a logo and link through to the
    # company rather than only naming it.
    company_id: Optional[int] = None
    company_logo_url: Optional[str] = None
    company_rating: Optional[float] = None
    company_rating_count: Optional[int] = None
    city: Optional[str]
    is_remote: bool
    remote_scope: Optional[str]
    min_exp_years: Optional[int]
    max_exp_years: Optional[int]
    salary_min: Optional[float]
    salary_max: Optional[float]
    salary_currency: str
    salary_period: str
    salary_disclosed: bool
    posted_date: Optional[datetime]
    apply_url: str
    source_name: Optional[str]
    # What the source board reports about the posting itself.
    poster_name: Optional[str] = None
    poster_title: Optional[str] = None
    source_applicant_count: Optional[int] = None
    has_description: bool = False
    score: float
    reasons: Dict[str, Any]
    explanation: Optional[str]
    state: str
    surfaced_at: datetime


class MatchListResponse(BaseModel):
    matches: List[MatchJobResponse]
    total_count: int
    page: int
    limit: int


class MatchStatsResponse(BaseModel):
    profile_id: int
    by_state: Dict[str, int]
    new_today: int
    total: int
