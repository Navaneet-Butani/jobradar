"""Custom exception classes."""

from typing import Any, Dict, Optional


class JobPortalException(Exception):
    """Base exception class for Job Portal application."""
    
    def __init__(
        self, 
        message: str, 
        error_code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationException(JobPortalException):
    """Exception for validation errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=400,
            details=details
        )


class AuthenticationException(JobPortalException):
    """Exception for authentication errors."""
    
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_REQUIRED",
            status_code=401
        )


class PermissionException(JobPortalException):
    """Exception for permission errors."""
    
    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            message=message,
            error_code="PERMISSION_DENIED",
            status_code=403
        )


class ResourceNotFoundException(JobPortalException):
    """Exception for resource not found errors."""
    
    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            message=message,
            error_code="RESOURCE_NOT_FOUND",
            status_code=404
        )


class RateLimitException(JobPortalException):
    """Exception for rate limit errors."""
    
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429
        )


class DatabaseException(JobPortalException):
    """Exception for database errors."""
    
    def __init__(self, message: str = "Database operation failed"):
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            status_code=500
        )


class ExternalAPIException(JobPortalException):
    """Exception for external API errors."""

    def __init__(self, message: str = "External API error"):
        super().__init__(
            message=message,
            error_code="EXTERNAL_API_ERROR",
            status_code=502
        )


class ProcessingException(JobPortalException):
    """Exception for data processing errors."""

    def __init__(self, message: str = "Data processing error"):
        super().__init__(
            message=message,
            error_code="PROCESSING_ERROR",
            status_code=500
        )


class LimitExceededException(JobPortalException):
    """Exception for subscription limit exceeded errors."""

    def __init__(self, message: str = "Subscription limit exceeded"):
        super().__init__(
            message=message,
            error_code="LIMIT_EXCEEDED",
            status_code=429
        )


class FeatureNotAvailableException(JobPortalException):
    """Exception for feature not available in subscription tier."""

    def __init__(self, message: str = "Feature not available in your subscription tier"):
        super().__init__(
            message=message,
            error_code="FEATURE_NOT_AVAILABLE",
            status_code=403
        )


class ConfigurationException(JobPortalException):
    """Exception for invalid or missing configuration."""

    def __init__(self, message: str = "Invalid configuration"):
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            status_code=500
        )


# Aliases for common usage patterns
ValidationError = ValidationException
AuthenticationError = AuthenticationException
PermissionError = PermissionException
ResourceNotFoundError = ResourceNotFoundException
NotFoundError = ResourceNotFoundException
RateLimitError = RateLimitException
DatabaseError = DatabaseException
ExternalAPIError = ExternalAPIException
ProcessingError = ProcessingException
LimitExceededError = LimitExceededException
FeatureNotAvailableError = FeatureNotAvailableException
ConfigurationError = ConfigurationException
