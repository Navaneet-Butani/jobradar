"""User login service with security features."""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from ...config.settings import settings
from ...core.security import SecurityManager
from ...core.redis import get_redis
from ...models import UserDB
from .token_service import TokenService, AuthTokens
from .session_service import SessionService, DeviceInfo
from .security_audit import SecurityAuditService


class LoginResult:
    """Login result model."""

    def __init__(self, success: bool, user: Optional[UserDB] = None, tokens: Optional[AuthTokens] = None, session_id: Optional[str] = None, message: str = "", errors: Optional[Dict[str, str]] = None, requires_verification: bool = False):
        self.success = success
        self.user = user
        self.tokens = tokens
        self.session_id = session_id
        self.message = message
        self.errors = errors or {}
        self.requires_verification = requires_verification


class LoginCredentials:
    """Login credentials model."""

    def __init__(self, email: str, password: str, remember_me: bool = False):
        self.email = email.lower().strip()
        self.password = password
        self.remember_me = remember_me


class LoginService:
    """User login service."""

    @staticmethod
    async def login(
        credentials: LoginCredentials,
        device_info: DeviceInfo,
        session: AsyncSession = None
    ) -> LoginResult:
        """Authenticate user and create session."""
        try:
            # Check rate limiting
            if await LoginService._is_rate_limited(credentials.email, device_info.ip_address):
                await SecurityAuditService.log_login_attempt(
                    user_id=None,
                    email=credentials.email,
                    success=False,
                    ip_address=device_info.ip_address,
                    user_agent=device_info.user_agent,
                    failure_reason="rate_limited",
                    session=session
                )

                return LoginResult(
                    success=False,
                    message="Too many login attempts. Please try again later.",
                    errors={"general": "Account temporarily locked due to multiple failed attempts"}
                )

            # Find user by email
            user = await LoginService._get_user_by_email(credentials.email, session)

            if not user:
                await LoginService._record_failed_attempt(credentials.email, device_info.ip_address, "user_not_found")
                await SecurityAuditService.log_login_attempt(
                    user_id=None,
                    email=credentials.email,
                    success=False,
                    ip_address=device_info.ip_address,
                    user_agent=device_info.user_agent,
                    failure_reason="user_not_found",
                    session=session
                )

                return LoginResult(
                    success=False,
                    message="Invalid email or password",
                    errors={"credentials": "The email or password you entered is incorrect"}
                )

            # Check if user is active
            if not user.is_active:
                await SecurityAuditService.log_login_attempt(
                    user_id=user.id,
                    email=credentials.email,
                    success=False,
                    ip_address=device_info.ip_address,
                    user_agent=device_info.user_agent,
                    failure_reason="account_inactive",
                    session=session
                )

                return LoginResult(
                    success=False,
                    message="Account is inactive",
                    errors={"account": "This account has been deactivated"}
                )

            # Verify password
            if not SecurityManager.verify_password(credentials.password, user.password_hash):
                await LoginService._record_failed_attempt(credentials.email, device_info.ip_address, "invalid_password")
                await SecurityAuditService.log_login_attempt(
                    user_id=user.id,
                    email=credentials.email,
                    success=False,
                    ip_address=device_info.ip_address,
                    user_agent=device_info.user_agent,
                    failure_reason="invalid_password",
                    session=session
                )

                return LoginResult(
                    success=False,
                    message="Invalid email or password",
                    errors={"credentials": "The email or password you entered is incorrect"}
                )

            # Check email verification if required
            if settings.require_email_verification and not user.email_verified:
                await SecurityAuditService.log_login_attempt(
                    user_id=user.id,
                    email=credentials.email,
                    success=False,
                    ip_address=device_info.ip_address,
                    user_agent=device_info.user_agent,
                    failure_reason="email_not_verified",
                    session=session
                )

                return LoginResult(
                    success=False,
                    message="Email verification required",
                    errors={"verification": "Please verify your email address before logging in"},
                    requires_verification=True
                )

            # Successful login - clear failed attempts
            await LoginService._clear_failed_attempts(credentials.email, device_info.ip_address)

            # Check for suspicious activity
            await SessionService.detect_suspicious_activity(user.id, device_info.ip_address, session)

            # Update last login
            user.last_login_at = datetime.utcnow()

            # Generate tokens first (without session_id initially)
            tokens = await TokenService.create_token_pair(user.id)
            refresh_token, refresh_expires = TokenService.create_refresh_token(user.id)

            # Create session with the refresh token
            session_id = await SessionService.create_session(
                user_id=user.id,
                device_info=device_info,
                refresh_token=refresh_token,
                refresh_token_expires=refresh_expires,
                session=session
            )

            # Regenerate tokens with session_id for security
            tokens = await TokenService.create_token_pair(user.id, session_id)

            await session.commit()

            # Log successful login
            await SecurityAuditService.log_login_attempt(
                user_id=user.id,
                email=credentials.email,
                success=True,
                ip_address=device_info.ip_address,
                user_agent=device_info.user_agent,
                session=session
            )

            return LoginResult(
                success=True,
                user=user,
                tokens=tokens,
                session_id=session_id,
                message="Login successful"
            )

        except Exception as e:
            await SecurityAuditService.log_login_attempt(
                user_id=None,
                email=credentials.email,
                success=False,
                ip_address=device_info.ip_address,
                user_agent=device_info.user_agent,
                failure_reason=f"system_error: {str(e)}",
                session=session
            )

            return LoginResult(
                success=False,
                message="Login failed",
                errors={"general": "An error occurred during login"}
            )

    @staticmethod
    async def logout(session_id: str, session: AsyncSession) -> bool:
        """Logout user by terminating session and revoking tokens."""
        # Get session info before terminating
        user_session = await SessionService.get_session(session_id, session)

        if not user_session:
            return False

        # Terminate the session first
        success = await SessionService.terminate_session(session_id, session, "logout")

        if success:
            # CRITICAL SECURITY: Revoke the refresh token associated with this session
            if user_session.refresh_token:
                try:
                    # Decode refresh token to get JTI for revocation
                    import jwt
                    payload = jwt.decode(
                        user_session.refresh_token,
                        options={"verify_signature": False}
                    )
                    jti = payload.get("jti")

                    if jti:
                        await TokenService.revoke_token(
                            jti,
                            user_session.user_id,
                            session,
                            "logout",
                            # Straight from the payload decoded just above;
                            # revoke_token can no longer work these out itself.
                            token_type=payload.get("type", "refresh"),
                            expires_at=datetime.fromtimestamp(payload["exp"]) if payload.get("exp") else None,
                        )
                except Exception:
                    # If we can't decode the token, still log the logout
                    pass

            # Log successful logout
            await SecurityAuditService.log_authentication_event(
                event_type="logout",
                user_id=user_session.user_id,
                success=True,
                ip_address=user_session.ip_address,
                user_agent=user_session.user_agent,
                session=session
            )

        return success

    @staticmethod
    async def logout_all_devices(user_id: int, current_session_id: Optional[str], session: AsyncSession) -> int:
        """Logout user from all devices except current."""
        # First get all sessions to revoke their tokens
        user_sessions = await SessionService.get_user_sessions(user_id, session)

        # Revoke tokens for sessions that will be terminated
        for session_info in user_sessions:
            if current_session_id and session_info.session_id == current_session_id:
                continue  # Skip current session

            # Get the actual session object to access refresh token
            user_session = await SessionService.get_session(session_info.session_id, session)
            if user_session and user_session.refresh_token:
                try:
                    # Decode refresh token to get JTI for revocation
                    import jwt
                    payload = jwt.decode(
                        user_session.refresh_token,
                        options={"verify_signature": False}
                    )
                    jti = payload.get("jti")

                    if jti:
                        await TokenService.revoke_token(
                            jti,
                            user_id,
                            session,
                            "logout_all_devices",
                            token_type=payload.get("type", "refresh"),
                            expires_at=datetime.fromtimestamp(payload["exp"]) if payload.get("exp") else None,
                        )
                except Exception:
                    # If we can't decode the token, continue with session termination
                    pass

        # Terminate all sessions
        terminated_count = await SessionService.terminate_all_user_sessions(
            user_id=user_id,
            session=session,
            exclude_session=current_session_id,
            reason="logout_all_devices"
        )

        return terminated_count

    @staticmethod
    async def refresh_tokens(refresh_token: str, session: AsyncSession) -> LoginResult:
        """Refresh access token using refresh token."""
        try:
            tokens = await TokenService.refresh_tokens(refresh_token, session)

            return LoginResult(
                success=True,
                tokens=tokens,
                message="Tokens refreshed successfully"
            )

        except Exception as e:
            return LoginResult(
                success=False,
                message="Token refresh failed",
                errors={"token": str(e)}
            )

    @staticmethod
    async def _get_user_by_email(email: str, session: AsyncSession) -> Optional[UserDB]:
        """Get user by email."""
        result = await session.execute(
            select(UserDB).where(UserDB.email == email.lower())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _is_rate_limited(email: str, ip_address: str) -> bool:
        """Check if email or IP is rate limited."""
        redis = get_redis()
        if redis is None:
            # Matches the rest of the app's Redis-down behavior (see
            # middleware.rate_limit): fail open rather than block login.
            return False

        # Rate limit keys
        email_key = f"login_attempts:email:{email}"
        ip_key = f"login_attempts:ip:{ip_address}"

        # Check attempts
        email_attempts = await redis.get(email_key)
        ip_attempts = await redis.get(ip_key)

        max_attempts = settings.max_login_attempts

        return (
            (email_attempts and int(email_attempts) >= max_attempts) or
            (ip_attempts and int(ip_attempts) >= max_attempts)
        )

    @staticmethod
    async def _record_failed_attempt(email: str, ip_address: str, reason: str) -> None:
        """Record failed login attempt."""
        redis = get_redis()
        if redis is None:
            return

        # Rate limit keys
        email_key = f"login_attempts:email:{email}"
        ip_key = f"login_attempts:ip:{ip_address}"

        # Increment attempts with expiration
        lockout_duration = settings.account_lockout_duration_minutes * 60

        # Use pipeline for atomic operations
        pipe = redis.pipeline()
        pipe.incr(email_key)
        pipe.expire(email_key, lockout_duration)
        pipe.incr(ip_key)
        pipe.expire(ip_key, lockout_duration)
        await pipe.execute()

    @staticmethod
    async def _clear_failed_attempts(email: str, ip_address: str) -> None:
        """Clear failed login attempts on successful login."""
        redis = get_redis()
        if redis is None:
            return

        # Clear rate limit counters
        email_key = f"login_attempts:email:{email}"
        ip_key = f"login_attempts:ip:{ip_address}"

        await redis.delete(email_key, ip_key)

    @staticmethod
    async def get_login_attempts_info(email: str, ip_address: str) -> Dict[str, Any]:
        """Get information about login attempts for debugging."""
        redis = get_redis()
        if redis is None:
            return {
                "email_attempts": 0, "ip_attempts": 0,
                "email_lockout_remaining": 0, "ip_lockout_remaining": 0,
                "max_attempts": settings.max_login_attempts,
            }

        email_key = f"login_attempts:email:{email}"
        ip_key = f"login_attempts:ip:{ip_address}"

        email_attempts = await redis.get(email_key)
        ip_attempts = await redis.get(ip_key)

        email_ttl = await redis.ttl(email_key)
        ip_ttl = await redis.ttl(ip_key)

        return {
            "email_attempts": int(email_attempts) if email_attempts else 0,
            "ip_attempts": int(ip_attempts) if ip_attempts else 0,
            "email_lockout_remaining": email_ttl if email_ttl > 0 else 0,
            "ip_lockout_remaining": ip_ttl if ip_ttl > 0 else 0,
            "max_attempts": settings.max_login_attempts
        }