"""Pydantic models for the resume API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ResumeResponse(BaseModel):
    """The stored file's bytes are deliberately not exposed — only its size."""
    id: int
    filename: str
    content_type: Optional[str]
    char_count: int
    content_text: str
    file_size: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
