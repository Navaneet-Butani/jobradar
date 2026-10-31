"""Application settings using Pydantic Settings."""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")  # optional; app runs without it
    
    # Security
    secret_key: str = Field(..., env="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, env="REFRESH_TOKEN_EXPIRE_DAYS")


    # Frontend URL — used to build links inside emails (dashboard, apply, etc.)
    frontend_url: str = Field(default="http://localhost:3000", env="FRONTEND_URL")

    # Email Configuration - Amazon SES (unused while EMAIL_TRANSPORT=smtp)
    aws_access_key_id: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field(default="us-east-1", env="AWS_REGION")
    ses_from_email: str = Field(default="noreply@example.com", env="SES_FROM_EMAIL")
    ses_from_name: str = Field(default="JobRadar", env="SES_FROM_NAME")
    ses_rate_limit: int = Field(default=14, env="SES_RATE_LIMIT")  # emails per second

    # Email Queue Configuration
    email_queue_name: str = Field(default="email_queue", env="EMAIL_QUEUE_NAME")
    email_queue_retry_attempts: int = Field(default=3, env="EMAIL_QUEUE_RETRY_ATTEMPTS")
    email_queue_rate_limit: int = Field(default=14, env="EMAIL_QUEUE_RATE_LIMIT")

    # Email Template Configuration
    email_template_dir: str = Field(default="app/services/email/templates", env="EMAIL_TEMPLATE_DIR")

    # "smtp" (default, ₹0/month), "resend", or "ses" — which client EmailService
    # sends system mail through. Outreach never uses this; it sends per-user.
    email_transport: str = Field(default="smtp", env="EMAIL_TRANSPORT")

    # Resend — free tier ~100/day, 3k/month. Needs SES_FROM_EMAIL on a domain
    # verified in Resend.
    resend_api_key: Optional[str] = Field(default=None, env="RESEND_API_KEY")

    # SMTP Configuration
    smtp_host: Optional[str] = Field(default=None, env="SMTP_HOST")
    smtp_port: int = Field(default=587, env="SMTP_PORT")
    smtp_username: Optional[str] = Field(default=None, env="SMTP_USERNAME")
    smtp_password: Optional[str] = Field(default=None, env="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, env="SMTP_USE_TLS")
    from_email: Optional[str] = Field(default=None, env="FROM_EMAIL")

    # Token Expiration Settings
    email_verification_expire_hours: int = Field(default=24, env="EMAIL_VERIFICATION_EXPIRE_HOURS")
    password_reset_expire_hours: int = Field(default=1, env="PASSWORD_RESET_EXPIRE_HOURS")

    # Session Configuration
    session_expire_days: int = Field(default=30, env="SESSION_EXPIRE_DAYS")
    max_sessions_per_user: int = Field(default=5, env="MAX_SESSIONS_PER_USER")

    # Security Settings
    max_login_attempts: int = Field(default=5, env="MAX_LOGIN_ATTEMPTS")
    account_lockout_duration_minutes: int = Field(default=15, env="ACCOUNT_LOCKOUT_DURATION_MINUTES")
    password_min_length: int = Field(default=8, env="PASSWORD_MIN_LENGTH")
    require_email_verification: bool = Field(default=True, env="REQUIRE_EMAIL_VERIFICATION")
    # Invite-only by default: the first admin is created with
    # `python -m scripts.create_admin`, everyone else through invites. Left
    # open, /auth/register would let anyone who finds the API URL sign up.
    allow_registration: bool = Field(default=False, env="ALLOW_REGISTRATION")
    
    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:3000"], 
        env="CORS_ORIGINS"
    )
    
    # Rate Limiting
    rate_limit_requests: int = Field(default=100, env="RATE_LIMIT_REQUESTS")
    rate_limit_period: int = Field(default=60, env="RATE_LIMIT_PERIOD")

    # The API and the ingest job share this codebase but not their shape: the
    # API is a small instance answering a handful of people, while ingest
    # processes jobs concurrently and starves at a small pool -- at 3+2 it
    # spent 10s timing out per job and wrote 1 row in 50 minutes.
    # Raising it is only safe on Supabase's TRANSACTION pooler (port 6543);
    # session mode (5432) caps the whole project at 15 clients.
    db_pool_size: int = Field(default=3, env="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=2, env="DB_MAX_OVERFLOW")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    

    # LLM re-rank (Phase 2 matching) — absent key means llm_rerank.py no-ops
    gemini_api_key: Optional[str] = Field(default=None, env="GEMINI_API_KEY")
    # Or any OpenAI-compatible endpoint (takes precedence over Gemini when set):
    # OpenAI, Groq, OpenRouter, or a local Ollama at http://localhost:11434/v1
    llm_base_url: Optional[str] = Field(default=None, env="LLM_BASE_URL")
    llm_api_key: Optional[str] = Field(default=None, env="LLM_API_KEY")
    llm_model: str = Field(default="llama3.1", env="LLM_MODEL")

    # Chat alerts: only matches scoring at least this are pushed to profile webhooks
    notify_min_score: float = Field(default=60, env="NOTIFY_MIN_SCORE")
    
    # RemoteOK API Integration
    remoteok_base_url: str = Field(
        default="https://remoteok.io/api",
        env="REMOTEOK_BASE_URL"
    )
    remoteok_rate_limit_calls: int = Field(default=1, env="REMOTEOK_RATE_LIMIT_CALLS")
    remoteok_rate_limit_window: int = Field(default=1, env="REMOTEOK_RATE_LIMIT_WINDOW")


    # Instahyre API Integration
    instahyre_base_url: str = Field(
        default="https://www.instahyre.com/api/v1/job_search",
        env="INSTAHYRE_BASE_URL"
    )
    instahyre_rate_limit_calls: int = Field(default=1, env="INSTAHYRE_RATE_LIMIT_CALLS")
    instahyre_rate_limit_window: int = Field(default=1, env="INSTAHYRE_RATE_LIMIT_WINDOW")
    instahyre_enabled: bool = Field(default=False, env="INSTAHYRE_ENABLED")

    # Remote job boards (Phase 3 Task 6.2) — heavily US/EU-weighted, kept off by default
    arbeitnow_base_url: str = Field(default="https://www.arbeitnow.com/api/job-board-api", env="ARBEITNOW_BASE_URL")
    arbeitnow_enabled: bool = Field(default=False, env="ARBEITNOW_ENABLED")

    remotive_base_url: str = Field(default="https://remotive.com/api/remote-jobs", env="REMOTIVE_BASE_URL")
    remotive_enabled: bool = Field(default=False, env="REMOTIVE_ENABLED")

    himalayas_base_url: str = Field(default="https://himalayas.app/jobs/api", env="HIMALAYAS_BASE_URL")
    himalayas_enabled: bool = Field(default=False, env="HIMALAYAS_ENABLED")

    # Hirist (Phase 3 Task 6.1) — India tech-only, undocumented JSON API
    hirist_enabled: bool = Field(default=False, env="HIRIST_ENABLED")

    # Timezone used for "today" (daily outreach cap, digests, follow-up dates)
    app_timezone: str = Field(default="Asia/Kolkata", env="APP_TIMEZONE")

    # Environment
    environment: str = Field(default="development", env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


PLACEHOLDER_SECRET_KEYS = {"", "change-me", "your-secret-key-here-change-in-production"}

# Global settings instance
settings = Settings()

# SECRET_KEY signs every login token AND derives the key that encrypts stored
# SMTP passwords. A copied-from-example value in production would let anyone
# forge sessions, so refuse to start rather than run insecurely.
if settings.environment == "production" and (
    settings.secret_key in PLACEHOLDER_SECRET_KEYS or len(settings.secret_key) < 32
):
    raise RuntimeError(
        "SECRET_KEY is a placeholder or shorter than 32 characters. Generate one with: "
        "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )
