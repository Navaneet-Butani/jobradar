"""Enhanced API decorators for FastAPI validation and response handling."""

from functools import wraps
from typing import Callable, Type, Optional, Any, Dict
from fastapi import HTTPException, status, Request
from pydantic import BaseModel, ValidationError
import logging
import json
from datetime import datetime

from ..core.responses import APIResponse
from ..core.logger import get_logger

logger = get_logger(__name__)


def standardize_response(
    success_message: str = "Operation successful",
    error_message: str = "Operation failed"
):
    """
    Decorator to standardize API response format.
    Works with FastAPI's automatic serialization.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # Execute the original function
                result = await func(*args, **kwargs)
                
                # If result is already a JSONResponse, return as-is
                if hasattr(result, 'status_code'):
                    return result
                
                # Wrap result in standardized success response
                return APIResponse.success(
                    data=result,
                    message=success_message
                )
                
            except ValidationError as e:
                logger.warning(f"Validation error in {func.__name__}: {e}")
                return APIResponse.validation_error(
                    message="Input validation failed",
                    details={"validation_errors": e.errors()}
                )
            except HTTPException:
                # Re-raise HTTPExceptions to let FastAPI handle them
                raise
            except Exception as e:
                logger.error(f"Unexpected error in {func.__name__}: {e}")
                return APIResponse.error(
                    message=error_message,
                    error_code="INTERNAL_SERVER_ERROR",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return wrapper
    return decorator


def validate_and_serialize(
    request_model: Optional[Type[BaseModel]] = None,
    response_model: Optional[Type[BaseModel]] = None,
    success_message: str = "Operation successful"
):
    """
    Decorator for additional validation beyond FastAPI's built-in validation.
    Useful for complex business logic validation.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = datetime.utcnow()
            
            try:
                # Log request start
                logger.info(f"Starting {func.__name__}")
                
                # Execute function
                result = await func(*args, **kwargs)
                
                # Apply response model if specified
                if response_model and isinstance(result, dict):
                    try:
                        validated_result = response_model(**result)
                        result = validated_result.dict()
                    except ValidationError as e:
                        logger.error(f"Response validation failed in {func.__name__}: {e}")
                        return APIResponse.error(
                            message="Response serialization failed",
                            error_code="SERIALIZATION_ERROR",
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
                
                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"Completed {func.__name__} in {execution_time:.3f}s")
                
                # Return standardized response
                return APIResponse.success(
                    data=result,
                    message=success_message
                )
                
            except ValidationError as e:
                logger.warning(f"Validation error in {func.__name__}: {e}")
                return APIResponse.validation_error(
                    message="Validation failed",
                    details={"validation_errors": e.errors()}
                )
            except HTTPException:
                raise
            except Exception as e:
                execution_time = (datetime.utcnow() - start_time).total_seconds()
                logger.error(f"Error in {func.__name__} after {execution_time:.3f}s: {e}")
                return APIResponse.error(
                    message="Internal server error",
                    error_code="INTERNAL_SERVER_ERROR",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return wrapper
    return decorator


def log_api_call(
    log_request: bool = True,
    log_response: bool = False,
    exclude_fields: Optional[list] = None
):
    """
    Decorator to log API calls for monitoring and debugging.
    """
    exclude_fields = exclude_fields or ['password', 'token', 'secret']
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = datetime.utcnow()
            
            # Log request if enabled
            if log_request:
                # Filter out sensitive fields
                safe_kwargs = {}
                for key, value in kwargs.items():
                    if key not in exclude_fields:
                        if hasattr(value, 'dict'):  # Pydantic model
                            model_dict = value.dict()
                            safe_dict = {k: v for k, v in model_dict.items() if k not in exclude_fields}
                            safe_kwargs[key] = safe_dict
                        else:
                            safe_kwargs[key] = value
                
                logger.info(f"API Call: {func.__name__} - Args: {safe_kwargs}")
            
            try:
                result = await func(*args, **kwargs)
                
                execution_time = (datetime.utcnow() - start_time).total_seconds()
                
                # Log response if enabled
                if log_response and not hasattr(result, 'status_code'):
                    logger.info(f"API Response: {func.__name__} - Data: {result}")
                
                logger.info(f"API Success: {func.__name__} completed in {execution_time:.3f}s")
                return result
                
            except Exception as e:
                execution_time = (datetime.utcnow() - start_time).total_seconds()
                logger.error(f"API Error: {func.__name__} failed after {execution_time:.3f}s - Error: {str(e)}")
                raise
        
        return wrapper
    return decorator


def require_auth(role: Optional[str] = None):
    """
    Decorator for authentication and authorization.
    Integrates with FastAPI's dependency injection system.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # This would integrate with your auth system
            # For now, it's a placeholder that can be extended
            
            # Extract request object from args/kwargs if present
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                # Look in kwargs
                request = kwargs.get('request')
            
            if request:
                # Extract auth token from headers
                auth_header = request.headers.get('Authorization')
                if not auth_header or not auth_header.startswith('Bearer '):
                    return APIResponse.unauthorized("Authentication token required")
                
                # Here you would validate the token and check roles
                # This is a placeholder for actual auth logic
                logger.info(f"Auth check passed for {func.__name__}")
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def handle_pagination():
    """
    Decorator to handle pagination parameters and validation.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract pagination parameters
            page = kwargs.get('page', 1)
            limit = kwargs.get('limit', 20)

            # Validate pagination parameters
            if not isinstance(page, int) or page < 1:
                return APIResponse.validation_error(
                    message="Page must be a positive integer",
                    details={"field": "page", "value": page}
                )

            if not isinstance(limit, int) or limit < 1 or limit > 100:
                return APIResponse.validation_error(
                    message="Limit must be between 1 and 100",
                    details={"field": "limit", "value": limit}
                )

            # Calculate offset
            offset = (page - 1) * limit
            kwargs['offset'] = offset

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def rate_limit(requests: int = 100, window: int = 60):
    """
    Decorator for basic rate limiting.

    Args:
        requests: Number of requests allowed
        window: Time window in seconds
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # Extract request object to get client IP
                request = None
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

                if not request:
                    request = kwargs.get('request')

                if request:
                    # Get client IP for rate limiting key
                    client_ip = request.client.host if request.client else "unknown"

                    # Create rate limit key
                    rate_limit_key = f"rate_limit:{func.__name__}:{client_ip}"

                    # TODO: Implement actual rate limiting with Redis
                    # For now, just log the attempt
                    logger.debug(f"Rate limit check for {rate_limit_key}: {requests}/{window}s")

                return await func(*args, **kwargs)

            except Exception as e:
                logger.warning(f"Rate limiting error: {e}")
                # Don't block request if rate limiting fails
                return await func(*args, **kwargs)

        return wrapper
    return decorator