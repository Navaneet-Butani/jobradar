"""Request logging middleware."""

import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..core.logger import get_logger, set_correlation_id, get_correlation_id

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests and responses."""
    
    async def dispatch(self, request: Request, call_next):
        """Process request with logging."""
        
        # Set correlation ID
        correlation_id_header = request.headers.get("X-Correlation-ID")
        correlation_id = set_correlation_id(correlation_id_header)
        
        # Get client IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        
        # Start timing
        start_time = time.time()
        
        # Log incoming request
        logger.info(
            f"Incoming request: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "ip": client_ip,
                "user_agent": request.headers.get("User-Agent", ""),
                "content_type": request.headers.get("Content-Type", ""),
                "content_length": request.headers.get("Content-Length", "0")
            }
        )
        
        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Calculate response time
            response_time = (time.time() - start_time) * 1000
            
            # Log error
            logger.error(
                f"Request failed: {request.method} {request.url.path}",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "ip": client_ip,
                    "response_time_ms": round(response_time, 2),
                    "error": str(e)
                }
            )
            raise
        
        # Calculate response time
        response_time = (time.time() - start_time) * 1000
        
        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        
        # Log completed request
        log_level = "error" if response.status_code >= 400 else "info"
        log_message = f"Request completed: {request.method} {request.url.path}"
        
        getattr(logger, log_level)(
            log_message,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "response_time_ms": round(response_time, 2),
                "ip": client_ip,
                "user_id": getattr(request.state, 'user_id', None),
                "content_length": response.headers.get("Content-Length", "0")
            }
        )
        
        # Add timing header
        response.headers["X-Response-Time"] = f"{response_time:.2f}ms"
        
        return response


def setup_request_logging(app):
    """Setup request logging middleware."""
    app.add_middleware(RequestLoggingMiddleware)
