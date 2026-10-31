"""Password management service for reset and change functionality."""

import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from ...config.settings import settings
from ...core.security import SecurityManager
from ...models import UserDB, PasswordResetTokenDB
from .token_service import TokenService
from .session_service import SessionService, DeviceInfo
from .security_audit import SecurityAuditService
from ..email import get_email_service


class PasswordResult:
    """Password operation result."""

    def __init__(self, success: bool, message: str = "", errors: Optional[Dict[str, str]] = None):
        self.success = success
        self.message = message
        self.errors = errors or {}


class PasswordService:
    """Password management service."""

    @staticmethod
    async def request_password_reset(
        email: str,
        device_info: DeviceInfo,
        session: AsyncSession = None
    ) -> PasswordResult:
        """Request password reset token."""
        try:
            # Find user by email
            result = await session.execute(
                select(UserDB).where(UserDB.email == email.lower())
            )
            user = result.scalar_one_or_none()

            if not user:
                # Don't reveal whether email exists for security
                await SecurityAuditService.log_password_reset_request(
                    email=email,
                    user_id=None,
                    ip_address=device_info.ip_address,
                    user_agent=device_info.user_agent,
                    session=session
                )

                return PasswordResult(
                    success=True,
                    message="If an account with this email exists, a password reset link has been sent."
                )

            # Check if user is active
            if not user.is_active:
                await SecurityAuditService.log_password_reset_request(
                    email=email,
                    user_id=user.id,
                    ip_address=device_info.ip_address,
                    user_agent=device_info.user_agent,
                    session=session
                )

                return PasswordResult(
                    success=True,
                    message="If an account with this email exists, a password reset link has been sent."
                )

            # Check rate limiting for password reset requests
            if await PasswordService._is_reset_rate_limited(user.id, session):
                return PasswordResult(
                    success=False,
                    message="Too many password reset requests. Please wait before requesting again.",
                    errors={"rate_limit": "Password reset temporarily unavailable"}
                )

            # Invalidate any existing reset tokens
            await PasswordService._invalidate_existing_reset_tokens(user.id, session)

            # Generate reset token
            reset_token = secrets.token_urlsafe(64)
            expires_at = datetime.utcnow() + timedelta(hours=settings.password_reset_expire_hours)

            # Create reset token record
            password_reset = PasswordResetTokenDB(
                user_id=user.id,
                token=reset_token,
                expires_at=expires_at,
                ip_address=device_info.ip_address,
                user_agent=device_info.user_agent
            )

            session.add(password_reset)
            await session.commit()

            # Send password reset email using new email service
            email_service = get_email_service()
            user_name = None
            if hasattr(user, 'profile') and user.profile:
                user_name = f"{user.profile.first_name} {user.profile.last_name}".strip()

            email_sent = await email_service.send_password_reset_email(
                user_email=user.email,
                reset_token=reset_token,
                user_name=user_name or user.email.split('@')[0],
                ip_address=device_info.ip_address
            )

            # Log the password reset request
            await SecurityAuditService.log_password_reset_request(
                email=email,
                user_id=user.id,
                ip_address=device_info.ip_address,
                user_agent=device_info.user_agent,
                session=session
            )

            return PasswordResult(
                success=True,
                message="Password reset link has been sent to your email address."
            )

        except Exception as e:
            return PasswordResult(
                success=False,
                message="Failed to process password reset request",
                errors={"general": "An error occurred while processing your request"}
            )

    @staticmethod
    async def reset_password(
        token: str,
        new_password: str,
        device_info: DeviceInfo,
        session: AsyncSession = None
    ) -> PasswordResult:
        """Reset password using reset token."""
        try:
            # Validate new password
            password_validation = SecurityManager.validate_password_strength(new_password)
            if not password_validation["is_valid"]:
                return PasswordResult(
                    success=False,
                    message="Password does not meet requirements",
                    errors={"password": "; ".join(password_validation["errors"])}
                )

            # Find reset token
            result = await session.execute(
                select(PasswordResetTokenDB).where(
                    PasswordResetTokenDB.token == token
                )
            )
            reset_token_record = result.scalar_one_or_none()

            if not reset_token_record:
                return PasswordResult(
                    success=False,
                    message="Invalid or expired reset token",
                    errors={"token": "The password reset link is invalid"}
                )

            # Check if token is expired
            if reset_token_record.expires_at < datetime.utcnow():
                return PasswordResult(
                    success=False,
                    message="Password reset token has expired",
                    errors={"token": "The password reset link has expired"}
                )

            # Check if token was already used
            if reset_token_record.is_used:
                return PasswordResult(
                    success=False,
                    message="Password reset token has already been used",
                    errors={"token": "This password reset link has already been used"}
                )

            # Get user
            user = await session.get(UserDB, reset_token_record.user_id)
            if not user or not user.is_active:
                return PasswordResult(
                    success=False,
                    message="User account not found or inactive",
                    errors={"user": "User account is not available"}
                )

            # Update password
            user.password_hash = SecurityManager.hash_password(new_password)

            # Mark token as used
            reset_token_record.is_used = True
            reset_token_record.used_at = datetime.utcnow()

            # Invalidate all user sessions (force re-login)
            await SessionService.terminate_all_user_sessions(
                user_id=user.id,
                session=session,
                reason="password_reset"
            )

            # Revoke all user tokens
            await TokenService.revoke_all_user_tokens(
                user_id=user.id,
                session=session,
                reason="password_reset"
            )

            await session.commit()

            # Log successful password reset
            await SecurityAuditService.log_password_reset_completion(
                user_id=user.id,
                success=True,
                ip_address=device_info.ip_address,
                user_agent=device_info.user_agent,
                session=session
            )

            return PasswordResult(
                success=True,
                message="Password has been reset successfully. Please log in with your new password."
            )

        except Exception as e:
            return PasswordResult(
                success=False,
                message="Failed to reset password",
                errors={"general": "An error occurred while resetting your password"}
            )

    @staticmethod
    async def change_password(
        user_id: int,
        current_password: str,
        new_password: str,
        device_info: DeviceInfo,
        session: AsyncSession = None
    ) -> PasswordResult:
        """Change password for authenticated user."""
        try:
            # Get user
            user = await session.get(UserDB, user_id)
            if not user or not user.is_active:
                return PasswordResult(
                    success=False,
                    message="User not found or inactive",
                    errors={"user": "User account is not available"}
                )

            # Verify current password (if user has one - OAuth users might not)
            if user.password_hash:
                if not SecurityManager.verify_password(current_password, user.password_hash):
                    await SecurityAuditService.log_account_event(
                        event_type="password_change_failed",
                        user_id=user.id,
                        description="Password change failed - incorrect current password",
                        success=False,
                        severity="medium",
                        ip_address=device_info.ip_address,
                        session=session
                    )

                    return PasswordResult(
                        success=False,
                        message="Current password is incorrect",
                        errors={"current_password": "The current password you entered is incorrect"}
                    )

            # Validate new password
            password_validation = SecurityManager.validate_password_strength(new_password)
            if not password_validation["is_valid"]:
                return PasswordResult(
                    success=False,
                    message="New password does not meet requirements",
                    errors={"new_password": "; ".join(password_validation["errors"])}
                )

            # Check if new password is different from current
            if user.password_hash and SecurityManager.verify_password(new_password, user.password_hash):
                return PasswordResult(
                    success=False,
                    message="New password must be different from current password",
                    errors={"new_password": "Please choose a different password"}
                )

            # Update password
            user.password_hash = SecurityManager.hash_password(new_password)
            await session.commit()

            # Send password change notification
            email_service = get_email_service()
            user_name = None
            if hasattr(user, 'profile') and user.profile:
                user_name = f"{user.profile.first_name} {user.profile.last_name}".strip()

            await email_service.send_password_changed_notification(
                user_email=user.email,
                user_name=user_name or user.email.split('@')[0],
                ip_address=device_info.ip_address
            )

            # Log successful password change
            await SecurityAuditService.log_account_event(
                event_type="password_changed",
                user_id=user.id,
                description="Password changed successfully",
                success=True,
                severity="medium",
                ip_address=device_info.ip_address,
                session=session
            )

            return PasswordResult(
                success=True,
                message="Password has been changed successfully."
            )

        except Exception as e:
            return PasswordResult(
                success=False,
                message="Failed to change password",
                errors={"general": "An error occurred while changing your password"}
            )

    @staticmethod
    async def validate_reset_token(token: str, session: AsyncSession) -> bool:
        """Validate if reset token is valid and not expired."""
        try:
            result = await session.execute(
                select(PasswordResetTokenDB).where(
                    and_(
                        PasswordResetTokenDB.token == token,
                        PasswordResetTokenDB.is_used == False,
                        PasswordResetTokenDB.expires_at > datetime.utcnow()
                    )
                )
            )
            reset_token = result.scalar_one_or_none()
            return reset_token is not None

        except Exception:
            return False

    @staticmethod
    async def _is_reset_rate_limited(user_id: int, session: AsyncSession) -> bool:
        """Check if user has requested too many password resets recently."""
        # Check for reset requests in the last hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)

        result = await session.execute(
            select(PasswordResetTokenDB).where(
                and_(
                    PasswordResetTokenDB.user_id == user_id,
                    PasswordResetTokenDB.created_at > one_hour_ago
                )
            )
        )

        recent_requests = result.scalars().all()

        # Allow max 3 requests per hour
        return len(recent_requests) >= 3

    @staticmethod
    async def _invalidate_existing_reset_tokens(user_id: int, session: AsyncSession) -> None:
        """Invalidate any existing password reset tokens for user."""
        result = await session.execute(
            select(PasswordResetTokenDB).where(
                and_(
                    PasswordResetTokenDB.user_id == user_id,
                    PasswordResetTokenDB.is_used == False,
                    PasswordResetTokenDB.expires_at > datetime.utcnow()
                )
            )
        )

        existing_tokens = result.scalars().all()

        for token in existing_tokens:
            token.is_used = True
            token.used_at = datetime.utcnow()

        if existing_tokens:
            await session.commit()

    @staticmethod
    async def cleanup_expired_tokens(session: AsyncSession) -> int:
        """Clean up expired password reset tokens."""
        from sqlalchemy import delete

        result = await session.execute(
            delete(PasswordResetTokenDB).where(
                PasswordResetTokenDB.expires_at < datetime.utcnow()
            )
        )

        await session.commit()
        return result.rowcount

    @staticmethod
    async def get_reset_token_info(token: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        """Get information about a reset token (for debugging)."""
        try:
            result = await session.execute(
                select(PasswordResetTokenDB).where(
                    PasswordResetTokenDB.token == token
                )
            )
            reset_token = result.scalar_one_or_none()

            if not reset_token:
                return None

            return {
                "user_id": reset_token.user_id,
                "is_used": reset_token.is_used,
                "expires_at": reset_token.expires_at,
                "created_at": reset_token.created_at,
                "is_expired": reset_token.expires_at < datetime.utcnow(),
                "time_remaining": (reset_token.expires_at - datetime.utcnow()).total_seconds() if reset_token.expires_at > datetime.utcnow() else 0
            }

        except Exception:
            return None