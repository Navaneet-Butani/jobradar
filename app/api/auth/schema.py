"""Pydantic schemas for authentication API."""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Dict, Any, List
from datetime import datetime


# Request schemas
class UserRegistrationRequest(BaseModel):
    """User registration request schema."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="User password")
    first_name: Optional[str] = Field(None, max_length=100, description="User first name")
    last_name: Optional[str] = Field(None, max_length=100, description="User last name")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123!",
                "first_name": "John",
                "last_name": "Doe"
            }
        }


class LoginRequest(BaseModel):
    """User login request schema."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")
    remember_me: bool = Field(default=False, description="Remember login for extended period")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123!",
                "remember_me": False
            }
        }


class PasswordResetRequest(BaseModel):
    """Password reset request schema."""
    email: EmailStr = Field(..., description="User email address")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com"
            }
        }


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation schema."""
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=8, description="New password")

    class Config:
        json_schema_extra = {
            "example": {
                "token": "reset-token-here",
                "new_password": "NewSecurePass123!"
            }
        }


class PasswordChangeRequest(BaseModel):
    """Password change request schema."""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")

    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "OldPassword123!",
                "new_password": "NewSecurePass123!"
            }
        }


class TokenRefreshRequest(BaseModel):
    """Token refresh request schema."""
    refresh_token: str = Field(..., description="Refresh token")

    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "refresh-token-here"
            }
        }


class EmailVerificationRequest(BaseModel):
    """Email verification request schema."""
    token: str = Field(..., description="Email verification token")

    class Config:
        json_schema_extra = {
            "example": {
                "token": "verification-token-here"
            }
        }


class ResendVerificationRequest(BaseModel):
    """Resend verification email request schema."""
    email: EmailStr = Field(..., description="User email address")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com"
            }
        }


# Response schemas
class TokenResponse(BaseModel):
    """Token response schema."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "token_type": "Bearer",
                "expires_in": 1800
            }
        }


class UserProfileResponse(BaseModel):
    """User profile response schema."""
    id: int = Field(..., description="User ID")
    uuid: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    is_active: bool = Field(..., description="User active status")
    email_verified: bool = Field(..., description="Email verification status")
    is_admin: bool = Field(False, description="May change deployment-wide settings and invite users")
    last_login_at: Optional[datetime] = Field(None, description="Last login timestamp")
    created_at: datetime = Field(..., description="Account creation timestamp")
    profile_picture_url: Optional[str] = Field(None, description="Profile picture URL")
    google_id: Optional[str] = Field(None, description="Google OAuth ID")

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AuthResponse(BaseModel):
    """Complete authentication response schema."""
    user: UserProfileResponse = Field(..., description="User profile information")
    tokens: TokenResponse = Field(..., description="Authentication tokens")
    session_id: str = Field(..., description="Session ID")
    is_new_user: bool = Field(default=False, description="Whether this is a new user registration")

    class Config:
        json_schema_extra = {
            "example": {
                "user": {
                    "id": 1,
                    "uuid": "123e4567-e89b-12d3-a456-426614174000",
                    "email": "user@example.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "is_active": True,
                    "email_verified": True,
                    "last_login_at": "2025-01-01T12:00:00Z",
                    "created_at": "2025-01-01T10:00:00Z"
                },
                "tokens": {
                    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                    "token_type": "Bearer",
                    "expires_in": 1800
                },
                "session_id": "session-id-here",
                "is_new_user": False
            }
        }


class SessionInfo(BaseModel):
    """Session information schema."""
    session_id: str = Field(..., description="Session ID")
    device_info: Dict[str, Any] = Field(..., description="Device information")
    ip_address: Optional[str] = Field(None, description="IP address")
    created_at: datetime = Field(..., description="Session creation time")
    last_activity: datetime = Field(..., description="Last activity time")
    expires_at: datetime = Field(..., description="Session expiration time")
    is_current: bool = Field(default=False, description="Whether this is the current session")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class UserSessionsResponse(BaseModel):
    """User sessions response schema."""
    sessions: List[SessionInfo] = Field(..., description="List of user sessions")
    total_count: int = Field(..., description="Total number of sessions")

    class Config:
        json_schema_extra = {
            "example": {
                "sessions": [
                    {
                        "session_id": "session-1",
                        "device_info": {"browser": "Chrome", "platform": "Windows"},
                        "ip_address": "192.168.1.1",
                        "created_at": "2025-01-01T10:00:00Z",
                        "last_activity": "2025-01-01T12:00:00Z",
                        "expires_at": "2025-01-31T10:00:00Z",
                        "is_current": True
                    }
                ],
                "total_count": 1
            }
        }


class MessageResponse(BaseModel):
    """Simple message response schema."""
    message: str = Field(..., description="Response message")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Operation completed successfully"
            }
        }



class PasswordValidationResponse(BaseModel):
    """Password validation response schema."""
    is_valid: bool = Field(..., description="Whether password is valid")
    errors: List[str] = Field(default_factory=list, description="List of validation errors")
    strength: str = Field(..., description="Password strength level")

    class Config:
        json_schema_extra = {
            "example": {
                "is_valid": True,
                "errors": [],
                "strength": "strong"
            }
        }