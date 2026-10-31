"""Pydantic models for the application packet API."""

from typing import List, Optional

from pydantic import BaseModel, Field


class PacketRequest(BaseModel):
    job_id: int = Field(..., gt=0)
    profile_id: int = Field(..., gt=0)


class ApplyLink(BaseModel):
    url: str
    is_direct_ats: bool
    ats_label: Optional[str]
    note: str


class PacketContact(BaseModel):
    method: Optional[str]
    label: str
    email: Optional[str]
    url: Optional[str]
    note: str


class StandardAnswers(BaseModel):
    notice_period: Optional[str]
    current_ctc: Optional[str]
    expected_ctc: Optional[str]
    willing_to_relocate: str
    total_experience: str


class PacketResponse(BaseModel):
    job_id: int
    title: str
    company_name: Optional[str]
    apply: ApplyLink
    bullets: List[str]
    cover_note: Optional[str]
    contact: PacketContact
    answers: StandardAnswers
    resume_filename: Optional[str]
    warnings: List[str]
