"""Base models and common fields for job data processing."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TimestampMixin(BaseModel):
    """Mixin for created_at and updated_at timestamps."""
    
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class ProcessingResult(BaseModel):
    """Base class for processing operation results."""
    
    success: bool = Field(..., description="Whether the operation was successful")
    message: Optional[str] = Field(None, description="Result message or error description")
    errors: list[str] = Field(default_factory=list, description="List of errors encountered")
    
    
class ValidationResult(BaseModel):
    """Result of data validation operations."""

    is_valid: bool = Field(..., description="Whether the data is valid")
    confidence: float = Field(default=1.0, ge=0, le=1, description="Confidence in the validation result")
    issues: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")
    quality_metrics: dict = Field(default_factory=dict, description="Quality/spam scoring details (QualityMetrics.__dict__)")
    validation_timestamp: Optional[datetime] = Field(default=None, description="When validation ran")


class DeduplicationResult(BaseModel):
    """Result of deduplication analysis."""

    is_duplicate: bool = Field(..., description="Whether this is a duplicate")
    duplicate_count: int = Field(default=0, description="Number of potential duplicates found")
    confidence_score: float = Field(default=0.0, ge=0, le=1, description="Similarity score of the closest match")
    match_type: str = Field(default="no_duplicates", description="How the match was determined (exact_hash, high_similarity, ...)")
    duplicate_job_ids: list[int] = Field(default_factory=list, description="IDs of duplicate jobs")
    match_factors: Optional[dict] = Field(default=None, description="Per-factor similarity breakdown of the best match")
    processing_notes: list[str] = Field(default_factory=list, description="Notes from the deduplication run")
    last_duplicate_found: Optional[datetime] = Field(default=None, description="When the most recent duplicate was found")
    duplicate_sources: list[int] = Field(default_factory=list, description="Source IDs the duplicates came from")


class ProcessingStats(BaseModel):
    """Statistics for batch processing operations."""
    
    total_processed: int = Field(ge=0, description="Total items processed")
    successful: int = Field(ge=0, description="Successfully processed items")
    failed: int = Field(ge=0, description="Failed items")
    duplicates_found: int = Field(ge=0, description="Duplicates detected")
    processing_time_ms: int = Field(ge=0, description="Total processing time in milliseconds")
    errors: list[str] = Field(default_factory=list, description="Processing errors")