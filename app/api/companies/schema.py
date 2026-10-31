"""Pydantic models for the companies API."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class CompanyJobResponse(BaseModel):
    """One open role at the company, for the list on its profile page."""

    id: int
    title: str
    city: Optional[str]
    is_remote: bool
    remote_scope: Optional[str]
    min_exp_years: Optional[int]
    max_exp_years: Optional[int]
    salary_min: Optional[float]
    salary_max: Optional[float]
    salary_currency: str
    salary_disclosed: bool
    posted_date: Optional[datetime]
    first_seen_at: Optional[datetime]
    source_name: Optional[str]
    apply_url: str
    poster_name: Optional[str]
    source_applicant_count: Optional[int]


class CompanyResponse(BaseModel):
    """Everything we know about one employer.

    Almost all of it is mined out of stored raw payloads rather than fetched —
    see app/services/enrichment/raw_backfill.py. Any field can be null; the
    source that gave us the job may publish nothing about the company.
    """

    id: int
    name: str
    slug: str
    website: Optional[str]
    career_page_url: Optional[str]
    logo_url: Optional[str]
    tagline: Optional[str]
    description: Optional[str]
    industry: Optional[str]
    headquarters: Optional[str]
    founded_year: Optional[int]
    employee_count: Optional[int]
    employee_range: Optional[str]
    rating: Optional[float]
    rating_count: Optional[int]
    rating_url: Optional[str]
    rating_source: Optional[str]
    ats_type: Optional[str]
    contact_email: Optional[str]

    active_jobs: int
    sources: List[str]
    jobs: List[CompanyJobResponse]
