"""Pydantic models for the outreach API."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# --- sending identity -------------------------------------------------------

class EmailAccountRequest(BaseModel):
    from_name: str = Field(..., min_length=1, max_length=120)
    from_email: EmailStr
    smtp_username: EmailStr
    smtp_password: str = Field(..., min_length=8, max_length=200, description="Gmail App Password, not the account password")
    smtp_host: str = Field(default="smtp.gmail.com", max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    daily_send_cap: int = Field(default=25, ge=1, le=200)
    send_interval_seconds: int = Field(default=45, ge=5, le=3600)
    signature: Optional[str] = Field(None, max_length=2000)


class EmailAccountResponse(BaseModel):
    """Never includes the password, encrypted or otherwise."""
    id: int
    from_name: str
    from_email: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    daily_send_cap: int
    send_interval_seconds: int
    signature: Optional[str]
    is_verified: bool
    last_verified_at: Optional[datetime]
    last_synced_at: Optional[datetime]
    last_sync_error: Optional[str]
    sent_today: int
    remaining_today: int

    model_config = {"from_attributes": True}


class SyncResultResponse(BaseModel):
    scanned: int
    replies: int
    bounces: int
    followups_queued: int
    skipped_replied: int
    skipped_bounced: int
    error: Optional[str] = None


# --- contacts ---------------------------------------------------------------

class ContactRequest(BaseModel):
    email: EmailStr
    contact_name: Optional[str] = Field(None, max_length=150)
    company_name: Optional[str] = Field(None, max_length=255)
    title: Optional[str] = Field(None, max_length=150)
    role_hint: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class ContactUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    contact_name: Optional[str] = Field(None, max_length=150)
    company_name: Optional[str] = Field(None, max_length=255)
    title: Optional[str] = Field(None, max_length=150)
    role_hint: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class ContactResponse(BaseModel):
    id: int
    email: str
    contact_name: Optional[str]
    company_name: Optional[str]
    title: Optional[str]
    role_hint: Optional[str]
    notes: Optional[str]
    source: str
    last_emailed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactListResponse(BaseModel):
    contacts: List[ContactResponse]
    total_count: int


class ImportResultResponse(BaseModel):
    imported: int
    updated: int
    skipped: int
    problems: List[str]
    contacts: List[ContactResponse]


# --- campaigns --------------------------------------------------------------

class CampaignRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    subject_template: str = Field(..., min_length=1)
    body_template: str = Field(..., min_length=1)
    attach_resume: bool = True
    personalize_with_llm: bool = False
    followup_enabled: bool = True
    followup_after_days: int = Field(default=4, ge=1, le=60)
    followup_subject_template: Optional[str] = None
    followup_body_template: Optional[str] = None
    contact_ids: List[int] = Field(default_factory=list)


class CampaignUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    attach_resume: Optional[bool] = None
    personalize_with_llm: Optional[bool] = None
    followup_enabled: Optional[bool] = None
    followup_after_days: Optional[int] = Field(None, ge=1, le=60)
    followup_subject_template: Optional[str] = None
    followup_body_template: Optional[str] = None


class MessageResponse(BaseModel):
    id: int
    to_email: str
    to_name: Optional[str]
    company_name: Optional[str]
    subject: str
    body: str
    attached_resume: bool
    status: str
    error: Optional[str]
    sent_at: Optional[datetime]
    step: int = 1
    replied_at: Optional[datetime] = None
    reply_from: Optional[str] = None
    reply_snippet: Optional[str] = None
    bounced_at: Optional[datetime] = None
    bounce_reason: Optional[str] = None
    previously_emailed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CampaignResponse(BaseModel):
    id: int
    name: str
    subject_template: str
    body_template: str
    status: str
    attach_resume: bool
    personalize_with_llm: bool
    followup_enabled: bool = True
    followup_after_days: int = 4
    followup_subject_template: Optional[str] = None
    followup_body_template: Optional[str] = None
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    counts: dict
    messages: List[MessageResponse] = Field(default_factory=list)


class CampaignListResponse(BaseModel):
    campaigns: List[CampaignResponse]
    total_count: int


class PreviewRequest(BaseModel):
    subject_template: str = Field(..., min_length=1)
    body_template: str = Field(..., min_length=1)
    contact_ids: List[int] = Field(default_factory=list)
    attach_resume: bool = True
    limit: int = Field(default=5, ge=1, le=25)


class PreviewItem(BaseModel):
    contact_id: int
    to_email: str
    to_name: Optional[str]
    company_name: Optional[str]
    subject: str
    body: str
    previously_emailed_at: Optional[datetime]


class PreviewResponse(BaseModel):
    items: List[PreviewItem]
    total_selected: int
    remaining_today: int
    pacing_note: str
    warnings: List[str]


class StartCampaignResponse(BaseModel):
    campaign_id: int
    queued: int
    remaining_today: int
    pacing_note: str


# --- single send (application side) ----------------------------------------

class ApplicationSendRequest(BaseModel):
    application_id: int = Field(..., gt=0)
    to_email: EmailStr
    to_name: Optional[str] = Field(None, max_length=150)
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1)
    attach_resume: bool = True
    save_contact: bool = True


class ApplicationDraftResponse(BaseModel):
    subject: str
    body: str
    to_email: Optional[str]
    to_name: Optional[str]
    company_name: Optional[str]
    job_title: str
    previously_emailed_at: Optional[datetime]
    remaining_today: int
    warnings: List[str]


class SendResultResponse(BaseModel):
    message_id: int
    to_email: str
    status: str
    sent_at: Optional[datetime]
    remaining_today: int
