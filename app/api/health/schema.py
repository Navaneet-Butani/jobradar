"""Health module schemas for request and response models."""

from pydantic import BaseModel, Field
from typing import Dict, Any
from datetime import datetime


class HealthCheckResponse(BaseModel):
    """Response model for basic health check."""
    
    postgres: bool = Field(..., description="PostgreSQL database health status")
    redis: bool = Field(..., description="Redis cache health status")
    overall_status: bool = Field(..., description="Overall system health status")
    
    class Config:
        json_schema_extra = {
            "example": {
                "postgres": True,
                "redis": True,
                "overall_status": True
            }
        }


class DetailedHealthCheckResponse(BaseModel):
    """Response model for detailed health check."""
    
    database: Dict[str, Any] = Field(..., description="Database health information")
    cache: Dict[str, Any] = Field(..., description="Cache health information") 
    overall_health: bool = Field(..., description="Overall system health")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Health check timestamp")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        json_schema_extra = {
            "example": {
                "database": {
                    "status": "healthy",
                    "type": "PostgreSQL",
                    "connection_pool": "active"
                },
                "cache": {
                    "status": "healthy",
                    "type": "Redis",
                    "connection": "active"
                },
                "overall_health": True,
                "timestamp": "2024-01-01T12:00:00Z"
            }
        }


class ServiceHealthStatus(BaseModel):
    """Model for individual service health status."""
    
    name: str = Field(..., description="Service name")
    status: str = Field(..., description="Service status (healthy/unhealthy)")
    response_time_ms: float = Field(..., description="Service response time in milliseconds")
    last_check: datetime = Field(default_factory=datetime.utcnow, description="Last health check time")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional service details")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }