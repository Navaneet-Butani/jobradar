"""Request/response models for the scraping configuration API."""

from typing import List
from pydantic import BaseModel, Field


class RoleCategoryResponse(BaseModel):
    """One role category and whether the scrapers currently collect it."""

    key: str = Field(..., description="Stable identifier, e.g. 'backend'")
    label: str = Field(..., description="Human-readable name for the UI")
    enabled: bool = Field(..., description="Whether jobs in this category are collected")
    examples: List[str] = Field(default_factory=list, description="Sample titles that match")


class RoleCategoriesResponse(BaseModel):
    categories: List[RoleCategoryResponse]
    editable: bool = Field(..., description="Whether the current user may change these")


class RoleCategoriesUpdateRequest(BaseModel):
    enabled: List[str] = Field(..., description="Category keys to collect; everything else is skipped")
