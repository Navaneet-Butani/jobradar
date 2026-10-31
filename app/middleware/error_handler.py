"""Global error handling middleware."""

import traceback
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import ValidationError

from ..core.logger import get_logger
from ..core.exceptions import JobPortalException
from ..core.responses import APIResponse
from ..config.settings import settings

logger = get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Global error handling middleware."""
    
    async def dispatch(self, request: Request, call_next):
        """Process request with error handling."""
        
        try:
            return await call_next(request)
            
        except JobPortalException as e:
            # Handle custom application exceptions
            logger.error(
                f"Application error: {e.message}",
                extra={
                    "error_code": e.error_code,
                    "status_code": e.status_code,
                    "path": request.url.path,
                    "method": request.method,
                    "details": e.details
                }
            )
            
            return APIResponse.error(
                message=e.message,
                error_code=e.error_code,
                status_code=e.status_code,
                details=e.details if settings.debug else None
            )
            
        except RequestValidationError as e:
            # Handle FastAPI validation errors
            logger.warning(
                f"Validation error: {str(e)}",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "validation_errors": e.errors()
                }
            )
            
            return APIResponse.error(
                message="Validation failed",
                error_code="VALIDATION_ERROR",
                status_code=422,
                details={
                    "validation_errors": e.errors()
                }
            )
            
        except ValidationError as e:
            # Handle Pydantic validation errors
            logger.warning(
                f"Pydantic validation error: {str(e)}",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "validation_errors": e.errors()
                }
            )
            
            return APIResponse.error(
                message="Data validation failed",
                error_code="VALIDATION_ERROR", 
                status_code=422,
                details={
                    "validation_errors": e.errors()
                }
            )
            
        except HTTPException as e:
            # Handle FastAPI HTTP exceptions
            logger.warning(
                f"HTTP exception: {e.detail}",
                extra={
                    "status_code": e.status_code,
                    "path": request.url.path,
                    "method": request.method
                }
            )
            
            # Convert to our standard response format
            error_codes = {
                400: "VALIDATION_ERROR",
                401: "AUTHENTICATION_REQUIRED", 
                403: "PERMISSION_DENIED",
                404: "RESOURCE_NOT_FOUND",
                429: "RATE_LIMIT_EXCEEDED"
            }
            
            error_code = error_codes.get(e.status_code, "HTTP_ERROR")
            
            return APIResponse.error(
                message=e.detail,
                error_code=error_code,
                status_code=e.status_code
            )
            
        except Exception as e:
            # Handle unexpected exceptions
            error_id = f"error_{id(e)}"
            
            logger.error(
                f"Unexpected error [{error_id}]: {str(e)}",
                extra={
                    "error_id": error_id,
                    "path": request.url.path,
                    "method": request.method,
                    "traceback": traceback.format_exc() if settings.debug else None
                }
            )
            
            # Don't expose internal errors in production
            if settings.environment == "production":
                message = "An internal server error occurred"
                details = None
            else:
                message = f"Internal server error: {str(e)}"
                details = {
                    "error_id": error_id,
                    "traceback": traceback.format_exc()
                }
            
            return APIResponse.error(
                message=message,
                error_code="INTERNAL_SERVER_ERROR",
                status_code=500,
                details=details
            )


def setup_error_handling(app):
    """Setup error handling middleware."""
    app.add_middleware(ErrorHandlerMiddleware)
