"""Advanced token management service for JWT handling."""

import jwt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config.settings import settings
from ...core.database import db
from ...models import UserDB, RevokedTokenDB, UserSessionDB
from .security_audit import SecurityAuditService


class TokenPayload:
    """Token payload model."""

    def __init__(self, user_id: int, token_type: str, jti: str, exp: datetime, iat: datetime, session_id: Optional[str] = None):
        self.user_id = user_id
        self.token_type = token_type
        self.jti = jti
        self.exp = exp
        self.iat = iat
        self.session_id = session_id


class AuthTokens:
    """Authentication tokens response model."""

    def __init__(self, access_token: str, refresh_token: str, expires_in: int):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_in = expires_in
        self.token_type = "Bearer"


class TokenService:
    """Advanced token management service."""

    @staticmethod
    def _generate_jti() -> str:
        """Generate a unique JWT ID."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_access_token(user_id: int, session_id: Optional[str] = None, additional_claims: Optional[Dict] = None) -> str:
        """Create a JWT access token with JTI for revocation support."""
        now = datetime.utcnow()
        exp = now + timedelta(minutes=settings.access_token_expire_minutes)
        jti = TokenService._generate_jti()

        payload = {
            "sub": str(user_id),
            "type": "access",
            "jti": jti,
            "iat": now,
            "exp": exp
        }

        if session_id:
            payload["session_id"] = session_id

        if additional_claims:
            payload.update(additional_claims)

        token = jwt.encode(
            payload,
            settings.secret_key,
            algorithm=settings.jwt_algorithm
        )

        return token

    @staticmethod
    def create_refresh_token(user_id: int, session_id: Optional[str] = None) -> tuple[str, datetime]:
        """Create a refresh token with expiration."""
        now = datetime.utcnow()
        exp = now + timedelta(days=settings.refresh_token_expire_days)
        jti = TokenService._generate_jti()

        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "jti": jti,
            "iat": now,
            "exp": exp
        }

        if session_id:
            payload["session_id"] = session_id

        token = jwt.encode(
            payload,
            settings.secret_key,
            algorithm=settings.jwt_algorithm
        )

        return token, exp

    @staticmethod
    async def create_token_pair(user_id: int, session_id: Optional[str] = None) -> AuthTokens:
        """Create access and refresh token pair."""
        access_token = TokenService.create_access_token(user_id, session_id)
        refresh_token, _ = TokenService.create_refresh_token(user_id, session_id)

        return AuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.access_token_expire_minutes * 60
        )

    @staticmethod
    async def verify_token(token: str, expected_type: str = "access") -> TokenPayload:
        """Verify and decode a JWT token."""
        try:
            # Decode token
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.jwt_algorithm]
            )

            # Validate token type
            if payload.get("type") != expected_type:
                raise jwt.InvalidTokenError(f"Invalid token type. Expected {expected_type}")

            # Check if token is revoked
            jti = payload.get("jti")
            if jti and await TokenService.is_token_revoked(jti):
                raise jwt.InvalidTokenError("Token has been revoked")

            return TokenPayload(
                user_id=int(payload["sub"]),
                token_type=payload["type"],
                jti=jti,
                exp=datetime.fromtimestamp(payload["exp"]),
                iat=datetime.fromtimestamp(payload["iat"]),
                session_id=payload.get("session_id")
            )

        except jwt.ExpiredSignatureError:
            raise jwt.InvalidTokenError("Token has expired")
        except jwt.InvalidTokenError:
            raise
        except (jwt.PyJWTError, ValueError, KeyError, TypeError) as e:
            # Only genuine token problems become InvalidTokenError. This used
            # to be a bare `except Exception`, which also swallowed the
            # database failure from is_token_revoked's session -- so when the
            # connection pool was exhausted, a valid refresh token was
            # reported as invalid and the user was quietly logged out instead
            # of seeing an error. Infrastructure faults now propagate.
            raise jwt.InvalidTokenError(f"Invalid token: {str(e)}")

    @staticmethod
    async def refresh_tokens(refresh_token: str, session: AsyncSession) -> AuthTokens:
        """Refresh token pair using a valid refresh token."""
        # Verify refresh token
        token_payload = await TokenService.verify_token(refresh_token, "refresh")

        # Check if user still exists and is active
        user = await session.get(UserDB, token_payload.user_id)
        if not user or not user.is_active:
            await TokenService.revoke_token(
                token_payload.jti, token_payload.user_id, session, "user_inactive",
                token_type=token_payload.token_type, expires_at=token_payload.exp)
            raise jwt.InvalidTokenError("User is inactive or not found")

        # Revoke the used refresh token
        await TokenService.revoke_token(
            token_payload.jti, token_payload.user_id, session, "token_refresh",
            token_type=token_payload.token_type, expires_at=token_payload.exp)

        # Create new token pair with session_id
        return await TokenService.create_token_pair(token_payload.user_id, token_payload.session_id)

    @staticmethod
    async def revoke_token(
        jti: str,
        user_id: Optional[int],
        session: AsyncSession,
        reason: str = "manual",
        token_type: str = "refresh",
        expires_at: Optional[datetime] = None,
    ) -> None:
        """Revoke a token by adding it to the revoked tokens table.

        `token_type` and `expires_at` are supplied by the caller, which has
        already decoded the token. This used to try `jwt.decode(jti)` instead
        -- but jti is a random identifier, not a JWT, so that call always
        raised, fell through to token_type="unknown", and every INSERT was
        rejected by revoked_tokens_token_type_check, which permits only
        'access' or 'refresh'. Revocation therefore never once succeeded
        (revoked_tokens was empty in production), and since refresh_tokens
        revokes the token it consumes, every single token refresh failed with
        it -- logging people out 30 minutes after signing in.
        """
        if expires_at is None:
            # Outlives any refresh token we issue, so the row is never pruned
            # early by a cleanup pass.
            expires_at = datetime.utcnow() + timedelta(days=30)

        revoked_token = RevokedTokenDB(
            jti=jti,
            user_id=user_id,
            token_type=token_type,
            expires_at=expires_at,
            revocation_reason=reason
        )

        session.add(revoked_token)
        await session.commit()

        # Log the revocation
        await SecurityAuditService.log_event(
            event_type="token_revoked",
            event_category="security",
            description=f"Token revoked: {reason}",
            user_id=user_id,
            success=True,
            event_data={"jti": jti, "reason": reason, "token_type": token_type},
            session=session
        )

    @staticmethod
    async def is_token_revoked(jti: str) -> bool:
        """Check if a token is revoked."""
        async with db.get_session() as session:
            # jti is a unique column, not the PK — session.get() looks up by
            # PK and would try (and fail) to cast the jti string to the
            # integer id column.
            result = await session.execute(
                select(RevokedTokenDB.id).where(RevokedTokenDB.jti == jti)
            )
            return result.scalar_one_or_none() is not None

    @staticmethod
    async def revoke_all_user_tokens(user_id: int, session: AsyncSession, reason: str = "logout_all") -> None:
        """Revoke all tokens for a user (for logout from all devices)."""
        # This is a simplified implementation - in production, you'd want to track all issued tokens
        # For now, we'll rely on token expiration and add a user-specific revocation timestamp

        # Log the mass revocation
        await SecurityAuditService.log_event(
            event_type="all_tokens_revoked",
            event_category="security",
            description=f"All user tokens revoked: {reason}",
            user_id=user_id,
            success=True,
            event_data={"reason": reason},
            session=session
        )

    @staticmethod
    async def get_user_from_token(token: str) -> Optional[UserDB]:
        """Get user from a valid access token with session validation."""
        try:
            token_payload = await TokenService.verify_token(token, "access")

            async with db.get_session() as session:
                user = await session.get(UserDB, token_payload.user_id)

                if not user or not user.is_active:
                    return None

                # CRITICAL SECURITY: Validate that token's session is still active
                if token_payload.session_id:
                    from sqlalchemy import select, and_

                    result = await session.execute(
                        select(UserSessionDB).where(
                            and_(
                                UserSessionDB.session_id == token_payload.session_id,
                                UserSessionDB.user_id == token_payload.user_id,
                                UserSessionDB.is_active == True,
                                UserSessionDB.expires_at > datetime.utcnow()
                            )
                        )
                    )

                    user_session = result.scalar_one_or_none()

                    # If session doesn't exist or is inactive, token is invalid
                    if not user_session:
                        return None

                return user

        except jwt.InvalidTokenError:
            return None

    @staticmethod
    async def cleanup_expired_tokens(session: AsyncSession) -> int:
        """Clean up expired revoked tokens from database."""
        from sqlalchemy import delete

        result = await session.execute(
            delete(RevokedTokenDB).where(RevokedTokenDB.expires_at < datetime.utcnow())
        )

        await session.commit()
        return result.rowcount