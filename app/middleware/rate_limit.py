"""Rate limiting middleware using Redis."""

import asyncio
import time
from typing import Optional
import redis.asyncio as redis
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from ..config.settings import settings
from ..core.responses import APIResponse
from ..core.logger import get_logger

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-based rate limiting middleware."""
    
    def __init__(self, app, redis_url: str = None):
        super().__init__(app)
        self.redis_url = redis_url or settings.redis_url
        self.redis: Optional[redis.Redis] = None
        self.default_limit = settings.rate_limit_requests
        self.default_window = settings.rate_limit_period
        
    async def setup_redis(self):
        """Initialize Redis connection."""
        if not self.redis_url:  # no Redis configured: requests are not rate limited
            return
        if not self.redis:
            try:
                self.redis = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    retry_on_timeout=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Test connection
                await self.redis.ping()
                logger.info("Redis connection established for rate limiting")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self.redis = None
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        
        # Skip rate limiting for health checks and internal endpoints.
        # The real paths carry the /api/v1 prefix (main.py mounts the health
        # router at /api); the bare ones below never matched anything. That
        # mattered once an uptime pinger started hitting /api/v1/health/check
        # every 5 minutes to keep Render's free instance warm: each ping was
        # spending 4 Upstash commands (zremrangebyscore/zcard/zadd/expire) to
        # rate-limit a request that cannot be abused, ~25k commands a month
        # against a 500k free allowance.
        if request.url.path in [
            "/health", "/health/detailed", "/metrics",
            "/api/v1/health/ping", "/api/v1/health/check", "/api/v1/health/quick",
            "/api/v1/health/detailed", "/api/v1/health/services",
        ]:
            return await call_next(request)
        
        # Initialize Redis if not done
        if not self.redis:
            await self.setup_redis()
        
        # If Redis is not available, log and continue without rate limiting
        if not self.redis:
            logger.warning("Redis unavailable, skipping rate limiting")
            return await call_next(request)
        
        # Get client identifier (IP or user ID)
        client_id = self.get_client_identifier(request)
        
        # Get rate limit configuration for this endpoint
        limit, window = self.get_rate_limit_config(request)
        
        # Check rate limit
        try:
            allowed, remaining, reset_time = await self.check_rate_limit(
                client_id, limit, window
            )
            
            if not allowed:
                logger.warning(
                    f"Rate limit exceeded for client {client_id}",
                    extra={
                        "client_id": client_id,
                        "path": request.url.path,
                        "method": request.method
                    }
                )
                # Return, don't raise. Starlette's exception middleware sits
                # inside this one, so an HTTPException raised here is never
                # converted -- the client got a 500 (with a traceback when
                # DEBUG is on) instead of a 429.
                response = APIResponse.rate_limit_exceeded()
                response.headers["X-RateLimit-Limit"] = str(limit)
                response.headers["X-RateLimit-Remaining"] = "0"
                response.headers["X-RateLimit-Reset"] = str(reset_time)
                response.headers["Retry-After"] = str(max(1, reset_time - int(time.time())))
                return response
            
            # Process request
            response = await call_next(request)
            
            # Add rate limit headers
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_time)
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Rate limiting error: {e}")
            # Continue without rate limiting if there's an error
            return await call_next(request)
    
    def get_client_identifier(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        
        # Try to get user ID from request (if authenticated)
        user_id = getattr(request.state, 'user_id', None)
        if user_id:
            return f"user:{user_id}"
        
        # Use IP address
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Get the first IP in case of multiple proxies
            ip = forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host
        
        return f"ip:{ip}"
    
    def get_rate_limit_config(self, request: Request) -> tuple[int, int]:
        """Get rate limit configuration for the request."""
        
        # Default limits
        limit = self.default_limit
        window = self.default_window
        
        # Endpoint-specific limits (can be expanded)
        endpoint_limits = {
            "/api/v1/auth/login": (5, 60),  # 5 requests per minute for login
            "/api/v1/auth/register": (3, 60),  # 3 requests per minute for registration
            "/api/v1/jobs/search": (100, 60),  # 100 requests per minute for job search
        }
        
        path = request.url.path
        if path in endpoint_limits:
            limit, window = endpoint_limits[path]
        
        # Check if user has premium rate limits
        user_type = getattr(request.state, 'user_type', 'free')
        if user_type == 'premium':
            limit = min(limit * 5, 500)  # 5x limit for premium users, max 500
        
        return limit, window
    
    async def check_rate_limit(
        self, 
        client_id: str, 
        limit: int, 
        window: int
    ) -> tuple[bool, int, int]:
        """
        Check if request is within rate limit using sliding window.
        
        Returns:
            (allowed, remaining_requests, reset_timestamp)
        """
        current_time = int(time.time())
        key = f"rate_limit:{client_id}"
        
        try:
            # Use Redis pipeline for atomic operations
            pipe = self.redis.pipeline()
            
            # Remove expired entries
            pipe.zremrangebyscore(key, 0, current_time - window)
            
            # Count current requests in window
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(current_time): current_time})
            
            # Set expiration
            pipe.expire(key, window)
            
            results = await pipe.execute()
            current_requests = results[1]  # Count after cleanup
            
            # Check if limit is exceeded
            allowed = current_requests < limit
            remaining = max(0, limit - current_requests - 1)
            reset_time = current_time + window
            
            return allowed, remaining, reset_time
            
        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}")
            # Allow request if Redis fails
            return True, limit, current_time + window


def setup_rate_limiting(app):
    """Setup rate limiting middleware."""
    app.add_middleware(RateLimitMiddleware)
