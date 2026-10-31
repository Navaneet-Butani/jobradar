"""CORS middleware configuration."""

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

from ..config.settings import settings


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware."""
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=[
            "Accept",
            "Accept-Language",
            "Content-Language",
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-API-Key",
            "X-Correlation-ID"
        ],
        expose_headers=["X-Correlation-ID", "X-RateLimit-Remaining", "X-RateLimit-Reset"]
    )
