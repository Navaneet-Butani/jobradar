"""Main FastAPI application."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
import logging

from .config.settings import settings
from .core.logger import setup_logging
from .core.database import db
from .core.redis import redis_manager
from .middleware import (
    setup_cors,
    setup_rate_limiting,
    setup_request_logging,
    setup_error_handling
)
from .api.health import router as health_router
from .api.jobs import router as jobs_router
from .api.auth import router as auth_router
from .api.applications import router as applications_router
from .api.profiles import router as profiles_router
from .api.matches import router as matches_router
from .api.companies import router as companies_router
from .api.resume import router as resume_router
from .api.packet import router as packet_router
from .api.outreach import router as outreach_router
from .api.scraping import router as scraping_router
from .api.invites import router as invites_router
from .core.responses import APIResponse
from fastapi.exceptions import RequestValidationError

# Initialize logging first
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    
    # Startup
    logger.info("Starting up JobRadar API...")
    
    try:
        # Initialize database connection
        await db.connect()
        logger.info("Database connection established")
        
        # Alembic owns the schema (functions, triggers and the text-search
        # config live in migrations, not in the models), so never create_all.
        from sqlalchemy import text
        async with db.get_session() as session:
            if not (await session.execute(text("SELECT to_regclass('public.alembic_version')"))).scalar():
                raise RuntimeError("Database schema missing. Run: python -m alembic upgrade head")
        
        # Initialize Redis connection
        await redis_manager.connect()
        logger.info("Redis connection established")
        

        
        logger.info("JobRadar API startup completed")
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down JobRadar API...")
    
    try:
        # Close database connections
        await db.disconnect()
        await redis_manager.disconnect()
        logger.info("Database and Redis connections closed")
        

        # Additional cleanup tasks can be added here
        # - Close external API clients
        # - Clean up temporary files
        
        logger.info("JobRadar API shutdown completed")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    
    app = FastAPI(
        title="JobRadar API",
        description="Self-hosted job radar for Indian IT/software roles: ingest, dedupe, match, track",
        version="1.0.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
        lifespan=lifespan
    )
    
    # Add exception handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        """Handle FastAPI validation errors."""
        return APIResponse.error(
            message="Request validation failed",
            error_code="VALIDATION_ERROR",
            status_code=422,
            details={
                # ctx can hold the raw exception object, which is not JSON serialisable
                "validation_errors": [
                    {"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()
                ]
            }
        )
    
    # Setup middleware (order matters!)
    setup_error_handling(app)  # Should be first to catch all errors
    setup_request_logging(app)  # Log all requests
    setup_rate_limiting(app)    # Apply rate limiting
    setup_cors(app)            # Handle CORS last
    
    # API routes with global /api prefix
    app.include_router(auth_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(applications_router, prefix="/api")
    app.include_router(profiles_router, prefix="/api")
    app.include_router(matches_router, prefix="/api")
    app.include_router(companies_router, prefix="/api")
    app.include_router(resume_router, prefix="/api")
    app.include_router(packet_router, prefix="/api")
    app.include_router(outreach_router, prefix="/api")
    app.include_router(scraping_router, prefix="/api")
    app.include_router(invites_router, prefix="/api")
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        access_log=False  # We handle access logging in middleware
    )
