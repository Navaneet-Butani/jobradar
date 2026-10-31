"""User registration service."""

import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...config.settings import settings
from ...core.security import SecurityManager
from ...models import UserDB, UserProfileDB, EmailVerificationTokenDB
from .token_service import TokenService, AuthTokens
from .session_service import SessionService, DeviceInfo
from .security_audit import SecurityAuditService
from ..email import get_email_service


class RegistrationResult:
    """Registration result model."""

    def __init__(self, success: bool, user: Optional[UserDB] = None, tokens: Optional[AuthTokens] = None, session_id: Optional[str] = None, message: str = "", errors: Optional[Dict[str, str]] = None):
        self.success = success
        self.user = user
        self.tokens = tokens
        self.session_id = session_id
        self.message = message
        self.errors = errors or {}


class UserRegistration:
    """User registration data model."""

    def __init__(self, email: str, password: str, first_name: Optional[str] = None, last_name: Optional[str] = None):
        self.email = email.lower().strip()
        self.password = password
        self.first_name = first_name.strip() if first_name else None
        self.last_name = last_name.strip() if last_name else None


class RegistrationService:
    """User registration service."""

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format."""
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_pattern, email) is not None

    @staticmethod
    def validate_password(password: str) -> Dict[str, Any]:
        """Validate password strength."""
        errors = []

        if len(password) < settings.password_min_length:
            errors.append(f"Password must be at least {settings.password_min_length} characters long")

        if not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")

        if not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")

        if not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one number")

        # Optional special character requirement
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            errors.append("Password should contain at least one special character")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }

    @staticmethod
    async def check_email_availability(email: str, session: AsyncSession) -> bool:
        """Check if email is available for registration."""
        result = await session.execute(
            select(UserDB).where(UserDB.email == email.lower())
        )
        existing_user = result.scalar_one_or_none()
        return existing_user is None

    @staticmethod
    async def register_user(
        registration_data: UserRegistration,
        device_info: DeviceInfo,
        session: AsyncSession = None
    ) -> RegistrationResult:
        """Register a new user."""
        try:
            # Validate email format
            if not RegistrationService.validate_email(registration_data.email):
                return RegistrationResult(
                    success=False,
                    message="Invalid email format",
                    errors={"email": "Please provide a valid email address"}
                )

            # Check email availability
            if not await RegistrationService.check_email_availability(registration_data.email, session):
                return RegistrationResult(
                    success=False,
                    message="Email already registered",
                    errors={"email": "This email address is already registered"}
                )

            # Validate password
            password_validation = RegistrationService.validate_password(registration_data.password)
            if not password_validation["is_valid"]:
                return RegistrationResult(
                    success=False,
                    message="Password does not meet requirements",
                    errors={"password": "; ".join(password_validation["errors"])}
                )

            # Create user account
            user = await RegistrationService._create_user_account(registration_data, session)

            # Create user profile. Assign it onto `user` as well: the object was
            # built in-session, never queried, so the eager loader on the
            # relationship does not apply to it and _send_verification_email's
            # `user.profile` would emit a lazy SELECT -- sync IO inside async,
            # which raised MissingGreenlet and failed every registration.
            profile = await RegistrationService._create_user_profile(user.id, registration_data, session)
            user.profile = profile


            # Generate tokens and session
            tokens = await TokenService.create_token_pair(user.id)
            refresh_token, refresh_expires = TokenService.create_refresh_token(user.id)

            # Create session
            session_id = await SessionService.create_session(
                user_id=user.id,
                device_info=device_info,
                refresh_token=refresh_token,
                refresh_token_expires=refresh_expires,
                session=session
            )

            # Send welcome email and verification email if required
            if settings.require_email_verification:
                await RegistrationService._send_verification_email(user, device_info, session)
            else:
                # Send welcome email directly if no verification required
                email_service = get_email_service()
                user_name = f"{registration_data.first_name} {registration_data.last_name}".strip()
                if not user_name:
                    user_name = registration_data.email.split('@')[0]

                await email_service.send_welcome_email(
                    user_email=user.email,
                    user_name=user_name,
                    activation_token=""  # No activation needed
                )

            # Log successful registration
            await SecurityAuditService.log_registration_attempt(
                email=registration_data.email,
                success=True,
                user_id=user.id,
                ip_address=device_info.ip_address,
                user_agent=device_info.user_agent,
                session=session
            )

            return RegistrationResult(
                success=True,
                user=user,
                tokens=tokens,
                session_id=session_id,
                message="Account created successfully"
            )

        except Exception as e:
            # Log failed registration
            await SecurityAuditService.log_registration_attempt(
                email=registration_data.email,
                success=False,
                ip_address=device_info.ip_address,
                user_agent=device_info.user_agent,
                failure_reason=str(e),
                session=session
            )

            return RegistrationResult(
                success=False,
                message="Registration failed",
                errors={"general": "An error occurred during registration"}
            )

    @staticmethod
    async def _create_user_account(registration_data: UserRegistration, session: AsyncSession) -> UserDB:
        """Create user account in database."""
        # Hash password
        password_hash = SecurityManager.hash_password(registration_data.password)

        # Create user
        user = UserDB(
            email=registration_data.email,
            password_hash=password_hash,
            is_active=True,
            email_verified=not settings.require_email_verification  # Auto-verify if not required
        )

        session.add(user)
        await session.flush()  # Get user ID
        return user

    @staticmethod
    async def _create_user_profile(user_id: int, registration_data: UserRegistration, session: AsyncSession) -> UserProfileDB:
        """Create user profile."""
        profile = UserProfileDB(
            user_id=user_id,
            first_name=registration_data.first_name,
            last_name=registration_data.last_name
        )

        session.add(profile)
        await session.flush()
        return profile

    @staticmethod
    async def _send_verification_email(user: UserDB, device_info: DeviceInfo, session: AsyncSession) -> None:
        """Send email verification token."""
        # Generate verification token
        verification_token = SecurityManager.generate_api_key()
        expires_at = datetime.utcnow() + timedelta(hours=settings.email_verification_expire_hours)

        # Create verification record
        email_verification = EmailVerificationTokenDB(
            user_id=user.id,
            email=user.email,
            token=verification_token,
            expires_at=expires_at,
            ip_address=device_info.ip_address
        )

        session.add(email_verification)
        await session.commit()

        # Send verification email using new email service
        email_service = get_email_service()
        user_name = None
        if hasattr(user, 'profile') and user.profile:
            user_name = f"{user.profile.first_name} {user.profile.last_name}".strip()

        email_sent = await email_service.send_verification_email(
            user_email=user.email,
            verification_token=verification_token,
            user_name=user_name or user.email.split('@')[0]
        )

        # Log the email sending attempt
        await SecurityAuditService.log_account_event(
            event_type="verification_email_sent",
            user_id=user.id,
            description=f"Verification email {'sent' if email_sent else 'failed'} to {user.email}",
            event_data={"email": user.email, "token": verification_token, "success": email_sent},
            ip_address=device_info.ip_address,
            session=session
        )

    @staticmethod
    async def verify_email(token: str, session: AsyncSession) -> RegistrationResult:
        """Verify user email with token."""
        try:
            # Find verification token
            result = await session.execute(
                select(EmailVerificationTokenDB).where(
                    EmailVerificationTokenDB.token == token
                )
            )
            verification = result.scalar_one_or_none()

            if not verification:
                return RegistrationResult(
                    success=False,
                    message="Invalid verification token",
                    errors={"token": "Verification token is invalid"}
                )

            # Check if token is expired
            if verification.expires_at < datetime.utcnow():
                return RegistrationResult(
                    success=False,
                    message="Verification token has expired",
                    errors={"token": "Verification token has expired"}
                )

            # Check if already verified
            if verification.is_verified:
                return RegistrationResult(
                    success=False,
                    message="Email already verified",
                    errors={"token": "This email has already been verified"}
                )

            # Get user
            user = await session.get(UserDB, verification.user_id)
            if not user:
                return RegistrationResult(
                    success=False,
                    message="User not found",
                    errors={"user": "Associated user not found"}
                )

            # Mark email as verified
            verification.is_verified = True
            verification.verified_at = datetime.utcnow()
            verification.verification_attempts += 1

            user.email_verified = True

            await session.commit()

            # Log verification
            await SecurityAuditService.log_email_verification(
                user_id=user.id,
                email=user.email,
                success=True,
                session=session
            )

            return RegistrationResult(
                success=True,
                user=user,
                message="Email verified successfully"
            )

        except Exception as e:
            return RegistrationResult(
                success=False,
                message="Email verification failed",
                errors={"general": "An error occurred during verification"}
            )

    @staticmethod
    async def resend_verification_email(email: str, device_info: DeviceInfo, session: AsyncSession) -> RegistrationResult:
        """Resend verification email."""
        try:
            # Find user
            result = await session.execute(
                select(UserDB).where(UserDB.email == email.lower())
            )
            user = result.scalar_one_or_none()

            if not user:
                return RegistrationResult(
                    success=False,
                    message="User not found",
                    errors={"email": "No account found with this email address"}
                )

            # Check if already verified
            if user.email_verified:
                return RegistrationResult(
                    success=False,
                    message="Email already verified",
                    errors={"email": "This email address is already verified"}
                )

            # Send new verification email
            await RegistrationService._send_verification_email(user, device_info, session)

            return RegistrationResult(
                success=True,
                message="Verification email sent"
            )

        except Exception as e:
            return RegistrationResult(
                success=False,
                message="Failed to send verification email",
                errors={"general": "An error occurred while sending verification email"}
            )