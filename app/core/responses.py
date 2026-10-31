"""Standardized API response formats."""

from typing import Any, Dict, List, Optional, Union
from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


class APIResponse:
    """Standardized API response builder."""

    @staticmethod
    def success(
        data: Union[Dict[str, Any], List[Any], Any] = None,
        message: str = "Success",
        status_code: int = status.HTTP_200_OK
    ) -> JSONResponse:
        """Create a successful response."""
        return JSONResponse(
            status_code=status_code,
            content={
                "status": True,
                "data": jsonable_encoder(data),
                "message": message,
                "error": None,
                "error_message": None
            }
        )
    
    @staticmethod
    def error(
        message: str = "An error occurred",
        error_code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """Create an error response."""
        return JSONResponse(
            status_code=status_code,
            content={
                "status": False,
                "data": None,
                "message": None,
                "error": error_code,
                "error_message": message,
                "details": details
            }
        )
    
    @staticmethod
    def created(
        data: Union[Dict[str, Any], List[Any], Any] = None,
        message: str = "Resource created successfully"
    ) -> JSONResponse:
        """Create a 201 Created response."""
        return APIResponse.success(
            data=data,
            message=message,
            status_code=status.HTTP_201_CREATED
        )
    
    @staticmethod
    def no_content(message: str = "Operation completed successfully") -> JSONResponse:
        """Create a 204 No Content response."""
        return JSONResponse(
            status_code=status.HTTP_204_NO_CONTENT,
            content={
                "status": True,
                "data": None,
                "message": message,
                "error": None,
                "error_message": None
            }
        )
    
    @staticmethod
    def validation_error(
        message: str = "Validation failed",
        details: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """Create a validation error response."""
        return APIResponse.error(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )
    
    @staticmethod
    def unauthorized(message: str = "Authentication required") -> JSONResponse:
        """Create an unauthorized response."""
        return APIResponse.error(
            message=message,
            error_code="AUTHENTICATION_REQUIRED",
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    
    @staticmethod
    def forbidden(message: str = "Permission denied") -> JSONResponse:
        """Create a forbidden response."""
        return APIResponse.error(
            message=message,
            error_code="PERMISSION_DENIED",
            status_code=status.HTTP_403_FORBIDDEN
        )
    
    @staticmethod
    def not_found(message: str = "Resource not found") -> JSONResponse:
        """Create a not found response."""
        return APIResponse.error(
            message=message,
            error_code="RESOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND
        )
    
    @staticmethod
    def rate_limit_exceeded(message: str = "Rate limit exceeded") -> JSONResponse:
        """Create a rate limit exceeded response."""
        return APIResponse.error(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS
        )
