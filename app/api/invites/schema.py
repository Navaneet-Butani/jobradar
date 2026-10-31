"""Request/response models for the invites API."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class InviteCreateRequest(BaseModel):
    email: EmailStr = Field(..., description="Who to invite")
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)


class InviteAcceptRequest(BaseModel):
    password: str = Field(..., min_length=8)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)


class MemberUpdateRequest(BaseModel):
    is_active: bool = Field(..., description="False signs the account out of future logins")


class MemberResponse(BaseModel):
    """One account, whether it has been claimed or is still a pending invite."""

    id: int
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool
    is_admin: bool
    is_self: bool = Field(False, description="True for the caller's own row")
    # Pending means invited but never claimed: no password has been set yet.
    pending: bool
    invite_url: Optional[str] = Field(None, description="Only present while pending")
    invite_expires_at: Optional[datetime] = None
    invite_expired: bool = False
    last_login_at: Optional[datetime] = None
    created_at: datetime


class MemberListResponse(BaseModel):
    members: List[MemberResponse]


class InviteCreateResponse(BaseModel):
    member: MemberResponse
    # Whether the invite mail actually left the building. The link is returned
    # either way -- on the free Resend tier mail to anyone but the account owner
    # is dropped, so copying the link is the path that always works.
    emailed: bool
    email_error: Optional[str] = None


class InvitePreviewResponse(BaseModel):
    """What the public accept page needs before anyone is logged in."""

    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    invited_by: Optional[str] = None
