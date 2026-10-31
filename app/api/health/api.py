"""Health API endpoints."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import List

from ...decorators.api_decorators import log_api_call, standardize_response
from ...core.responses import APIResponse
from .service import HealthService
from .schema import HealthCheckResponse, DetailedHealthCheckResponse, ServiceHealthStatus

router = APIRouter(prefix="/v1/health", tags=["health"])


@router.get(
    "/ping",
    summary="Liveness ping — no I/O",
    description="Returns 200 without touching Postgres or Redis. For keep-alive pings.",
)
async def ping() -> JSONResponse:
    """Cheapest possible 200.

    Render's free instance spins down after 15 idle minutes and takes ~50s to
    wake, so an external pinger keeps it warm during waking hours. The other
    health routes are the wrong tool for that: `/check` AND `/quick` both call
    HealthService.basic_health_check(), which queries Postgres and pings Redis
    — several thousand pointless round trips a month, each briefly holding one
    of the few pooled connections. This touches nothing, and it is in the rate
    limiter's skip list, so a ping costs zero Upstash commands too.

    Use /check, not this, when you want to know whether the service is
    actually healthy — this only proves the process is running.
    """
    return APIResponse.success(data={"status": "alive"}, message="pong")


@router.get(
    "/check",
    response_model=HealthCheckResponse,
    summary="Basic health check",
    description="Performs basic health check testing database and Redis connectivity"
)
@log_api_call(log_request=True)
async def health_check() -> JSONResponse:
    """
    Health check endpoint that tests database and Redis connectivity.
    
    Returns standardized response with PostgreSQL and Redis status.
    """
    try:
        health_status = await HealthService.basic_health_check()
        
        # Return success if all checks pass, otherwise partial success
        if health_status.overall_status:
            return APIResponse.success(
                data=health_status.dict(),
                message="All services are healthy"
            )
        elif health_status.postgres:
            return APIResponse.success(
                data=health_status.dict(),
                message="Database is healthy, Redis connection issues detected"
            )
        else:
            return APIResponse.error(
                message="Database connection failed",
                error_code="DATABASE_ERROR",
                status_code=503,
                details=health_status.dict()
            )
    
    except Exception as e:
        return APIResponse.error(
            message=f"Health check failed: {str(e)}",
            error_code="INTERNAL_SERVER_ERROR",
            status_code=500
        )


@router.get(
    "/detailed",
    response_model=DetailedHealthCheckResponse,
    summary="Detailed health check",
    description="Performs detailed health check with additional system information"
)
@log_api_call(log_request=True)
async def detailed_health_check() -> JSONResponse:
    """
    Detailed health check with additional system information.
    """
    try:
        health_status = await HealthService.detailed_health_check()
        
        if health_status.overall_health:
            return APIResponse.success(
                data=health_status.dict(),
                message="All systems operational"
            )
        else:
            return APIResponse.error(
                message="Some services are experiencing issues",
                error_code="EXTERNAL_API_ERROR",
                status_code=503,
                details=health_status.dict()
            )
            
    except Exception as e:
        return APIResponse.error(
            message=f"Health check failed: {str(e)}",
            error_code="INTERNAL_SERVER_ERROR",
            status_code=500
        )


@router.get(
    "/services",
    response_model=List[ServiceHealthStatus],
    summary="Service health status",
    description="Returns health status for all monitored services"
)
@log_api_call(log_request=True)
@standardize_response(success_message="Service health statuses retrieved successfully")
async def get_service_health() -> List[ServiceHealthStatus]:
    """Get health status for all monitored services."""
    return await HealthService.get_service_health_statuses()


@router.get(
    "/quick",
    summary="Quick health check",
    description="Returns a simple OK response for load balancer health checks"
)
async def quick_health_check() -> JSONResponse:
    """Quick health check for load balancers."""
    try:
        basic_health = await HealthService.basic_health_check()
        
        if basic_health.overall_status:
            return APIResponse.success(
                data={"status": "OK"},
                message="Service healthy"
            )
        else:
            return APIResponse.error(
                message="Service unhealthy",
                error_code="SERVICE_UNAVAILABLE",
                status_code=503,
                details={"status": "FAIL"}
            )
            
    except Exception as e:
        return APIResponse.error(
            message="Health check failed",
            error_code="INTERNAL_SERVER_ERROR", 
            status_code=500,
            details={"status": "ERROR", "error": str(e)}
        )