"""Session management service for tracking user sessions."""

import secrets
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_

from ...config.settings import settings
from ...models import UserSessionDB, UserDB
from .security_audit import SecurityAuditService


class DeviceInfo:
    """Device information model."""

    def __init__(self, user_agent: str = None, ip_address: str = None, platform: str = None, browser: str = None):
        self.user_agent = user_agent
        self.ip_address = ip_address
        self.platform = platform
        self.browser = browser

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_agent": self.user_agent,
            "ip_address": self.ip_address,
            "platform": self.platform,
            "browser": self.browser
        }


class SessionInfo:
    """Session information model."""

    def __init__(self, session_id: str, user_id: int, device_info: DeviceInfo, created_at: datetime, last_activity: datetime, expires_at: datetime):
        self.session_id = session_id
        self.user_id = user_id
        self.device_info = device_info
        self.created_at = created_at
        self.last_activity = last_activity
        self.expires_at = expires_at
        self.is_current = False


class SessionService:
    """Session management service."""

    @staticmethod
    def _generate_session_id() -> str:
        """Generate a unique session ID."""
        return secrets.token_urlsafe(64)

    @staticmethod
    async def create_session(
        user_id: int,
        device_info: DeviceInfo,
        refresh_token: str,
        refresh_token_expires: datetime,
        session: AsyncSession = None
    ) -> str:
        """Create a new user session."""
        session_id = SessionService._generate_session_id()
        expires_at = datetime.utcnow() + timedelta(days=settings.session_expire_days)

        # Check if user has too many active sessions
        await SessionService._cleanup_old_sessions(user_id, session)

        # Create new session
        user_session = UserSessionDB(
            user_id=user_id,
            session_id=session_id,
            refresh_token=refresh_token,
            refresh_token_expires=refresh_token_expires,
            device_info=device_info.to_dict(),
            ip_address=device_info.ip_address,
            user_agent=device_info.user_agent,
            expires_at=expires_at
        )

        session.add(user_session)
        await session.commit()

        # Log session creation
        await SecurityAuditService.log_event(
            event_type="session_created",
            event_category="authentication",
            description="New user session created",
            user_id=user_id,
            success=True,
            event_data={
                "session_id": session_id,
                "ip_address": device_info.ip_address,
                "user_agent": device_info.user_agent
            },
            session=session
        )

        return session_id

    @staticmethod
    async def get_session(session_id: str, session: AsyncSession) -> Optional[UserSessionDB]:
        """Get session by session ID."""
        result = await session.execute(
            select(UserSessionDB).where(
                and_(
                    UserSessionDB.session_id == session_id,
                    UserSessionDB.is_active == True,
                    UserSessionDB.expires_at > datetime.utcnow()
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_session_activity(session_id: str, session: AsyncSession) -> bool:
        """Update last activity timestamp for a session."""
        user_session = await SessionService.get_session(session_id, session)
        if user_session:
            user_session.last_activity = datetime.utcnow()
            await session.commit()
            return True
        return False

    @staticmethod
    async def validate_session(session_id: str, session: AsyncSession) -> Optional[UserDB]:
        """Validate session and return user if valid."""
        user_session = await SessionService.get_session(session_id, session)

        if not user_session:
            return None

        # Check if session is expired
        if user_session.expires_at < datetime.utcnow():
            await SessionService.terminate_session(session_id, session, "expired")
            return None

        # Get user and check if active
        user = await session.get(UserDB, user_session.user_id)
        if not user or not user.is_active:
            await SessionService.terminate_session(session_id, session, "user_inactive")
            return None

        # Update last activity
        await SessionService.update_session_activity(session_id, session)

        return user

    @staticmethod
    async def terminate_session(session_id: str, session: AsyncSession, reason: str = "logout") -> bool:
        """Terminate a specific session."""
        user_session = await SessionService.get_session(session_id, session)

        if not user_session:
            return False

        # Deactivate session
        user_session.is_active = False
        await session.commit()

        # Log session termination
        await SecurityAuditService.log_event(
            event_type="session_terminated",
            event_category="authentication",
            description=f"Session terminated: {reason}",
            user_id=user_session.user_id,
            success=True,
            event_data={
                "session_id": session_id,
                "reason": reason,
                "ip_address": user_session.ip_address
            },
            session=session
        )

        return True

    @staticmethod
    async def terminate_all_user_sessions(user_id: int, session: AsyncSession, exclude_session: Optional[str] = None, reason: str = "logout_all") -> int:
        """Terminate all sessions for a user, optionally excluding current session."""
        query = select(UserSessionDB).where(
            and_(
                UserSessionDB.user_id == user_id,
                UserSessionDB.is_active == True
            )
        )

        if exclude_session:
            query = query.where(UserSessionDB.session_id != exclude_session)

        result = await session.execute(query)
        sessions = result.scalars().all()

        terminated_count = 0
        for user_session in sessions:
            user_session.is_active = False
            terminated_count += 1

        await session.commit()

        # Log mass session termination
        await SecurityAuditService.log_event(
            event_type="all_sessions_terminated",
            event_category="security",
            description=f"All user sessions terminated: {reason}",
            user_id=user_id,
            success=True,
            event_data={
                "reason": reason,
                "terminated_count": terminated_count,
                "excluded_session": exclude_session
            },
            session=session
        )

        return terminated_count

    @staticmethod
    async def get_user_sessions(user_id: int, session: AsyncSession) -> List[SessionInfo]:
        """Get all active sessions for a user."""
        result = await session.execute(
            select(UserSessionDB).where(
                and_(
                    UserSessionDB.user_id == user_id,
                    UserSessionDB.is_active == True,
                    UserSessionDB.expires_at > datetime.utcnow()
                )
            ).order_by(UserSessionDB.last_activity.desc())
        )

        sessions = result.scalars().all()
        session_infos = []

        for user_session in sessions:
            device_info = DeviceInfo(
                user_agent=user_session.user_agent,
                ip_address=user_session.ip_address,
                **user_session.device_info or {}
            )

            session_info = SessionInfo(
                session_id=user_session.session_id,
                user_id=user_session.user_id,
                device_info=device_info,
                created_at=user_session.created_at,
                last_activity=user_session.last_activity,
                expires_at=user_session.expires_at
            )

            session_infos.append(session_info)

        return session_infos

    @staticmethod
    async def _cleanup_old_sessions(user_id: int, session: AsyncSession) -> None:
        """Clean up old/expired sessions and enforce session limits."""
        # First, remove expired sessions
        await session.execute(
            delete(UserSessionDB).where(
                and_(
                    UserSessionDB.user_id == user_id,
                    UserSessionDB.expires_at < datetime.utcnow()
                )
            )
        )

        # Count active sessions
        result = await session.execute(
            select(UserSessionDB).where(
                and_(
                    UserSessionDB.user_id == user_id,
                    UserSessionDB.is_active == True,
                    UserSessionDB.expires_at > datetime.utcnow()
                )
            ).order_by(UserSessionDB.last_activity.asc())
        )

        active_sessions = result.scalars().all()

        # If too many sessions, remove oldest ones
        max_sessions = settings.max_sessions_per_user
        if len(active_sessions) >= max_sessions:
            sessions_to_remove = active_sessions[:len(active_sessions) - max_sessions + 1]

            for old_session in sessions_to_remove:
                old_session.is_active = False

        await session.commit()

    @staticmethod
    async def update_refresh_token(session_id: str, new_refresh_token: str, expires_at: datetime, session: AsyncSession) -> bool:
        """Update refresh token for a session."""
        user_session = await SessionService.get_session(session_id, session)

        if user_session:
            user_session.refresh_token = new_refresh_token
            user_session.refresh_token_expires = expires_at
            await session.commit()
            return True

        return False

    @staticmethod
    async def detect_suspicious_activity(user_id: int, current_ip: str, session: AsyncSession) -> bool:
        """Detect potentially suspicious login activity."""
        # Get recent sessions for user
        recent_cutoff = datetime.utcnow() - timedelta(hours=24)

        result = await session.execute(
            select(UserSessionDB).where(
                and_(
                    UserSessionDB.user_id == user_id,
                    UserSessionDB.created_at > recent_cutoff
                )
            )
        )

        recent_sessions = result.scalars().all()

        # Check for login from new IP. asyncpg reads INET columns back as
        # ipaddress.IPv4Address/IPv6Address, not str, so stringify before
        # both the membership check and the JSONB event_data payload.
        known_ips = {str(s.ip_address) for s in recent_sessions if s.ip_address}

        if current_ip not in known_ips and len(known_ips) > 0:
            # Log suspicious activity
            await SecurityAuditService.log_event(
                event_type="suspicious_login_ip",
                event_category="security",
                description=f"Login from new IP address: {current_ip}",
                user_id=user_id,
                success=True,
                event_data={
                    "new_ip": current_ip,
                    "known_ips": list(known_ips)
                },
                session=session
            )
            return True

        return False