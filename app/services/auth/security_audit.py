"""Security audit logging service."""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import SecurityAuditLogDB


class SecurityAuditService:
    """Security audit logging service."""

    @staticmethod
    async def log_event(
        event_type: str,
        event_category: str,
        description: str,
        user_id: Optional[int] = None,
        success: bool = True,
        severity: str = "medium",
        event_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_path: Optional[str] = None,
        request_method: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """Log a security event."""

        # Create audit log entry
        audit_log = SecurityAuditLogDB(
            user_id=user_id,
            event_type=event_type,
            event_category=event_category,
            event_description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            request_path=request_path,
            request_method=request_method,
            event_data=event_data or {},
            severity=severity,
            success=success,
            error_message=error_message
        )

        if session:
            session.add(audit_log)
            await session.commit()

    @staticmethod
    async def log_authentication_event(
        event_type: str,
        user_id: Optional[int],
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """Log authentication-related events."""
        severity = "medium" if success else "high"

        await SecurityAuditService.log_event(
            event_type=event_type,
            event_category="authentication",
            description=f"Authentication event: {event_type}",
            user_id=user_id,
            success=success,
            severity=severity,
            event_data=event_data,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent,
            session=session
        )

    @staticmethod
    async def log_authorization_event(
        event_type: str,
        user_id: int,
        resource: str,
        action: str,
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_path: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """Log authorization-related events."""
        severity = "medium" if success else "high"

        await SecurityAuditService.log_event(
            event_type=event_type,
            event_category="authorization",
            description=f"Authorization {action} on {resource}",
            user_id=user_id,
            success=success,
            severity=severity,
            event_data={
                "resource": resource,
                "action": action,
                **(event_data or {})
            },
            ip_address=ip_address,
            user_agent=user_agent,
            request_path=request_path,
            session=session
        )

    @staticmethod
    async def log_account_event(
        event_type: str,
        user_id: int,
        description: str,
        success: bool = True,
        severity: str = "medium",
        event_data: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """Log account-related events."""
        await SecurityAuditService.log_event(
            event_type=event_type,
            event_category="account",
            description=description,
            user_id=user_id,
            success=success,
            severity=severity,
            event_data=event_data,
            ip_address=ip_address,
            user_agent=user_agent,
            session=session
        )

    @staticmethod
    async def log_security_event(
        event_type: str,
        description: str,
        user_id: Optional[int] = None,
        severity: str = "high",
        event_data: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """Log high-priority security events."""
        await SecurityAuditService.log_event(
            event_type=event_type,
            event_category="security",
            description=description,
            user_id=user_id,
            success=True,  # Security events are informational
            severity=severity,
            event_data=event_data,
            ip_address=ip_address,
            user_agent=user_agent,
            session=session
        )

    @staticmethod
    async def log_system_event(
        event_type: str,
        description: str,
        success: bool = True,
        severity: str = "low",
        event_data: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """Log system-related events."""
        await SecurityAuditService.log_event(
            event_type=event_type,
            event_category="system",
            description=description,
            success=success,
            severity=severity,
            event_data=event_data,
            session=session
        )

    # Convenience methods for common events

    @staticmethod
    async def log_login_attempt(
        user_id: Optional[int],
        email: str,
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """Log login attempt."""
        event_data = {"email": email}
        error_message = None

        if not success and failure_reason:
            error_message = failure_reason
            event_data["failure_reason"] = failure_reason

        await SecurityAuditService.log_authentication_event(
            event_type="login_attempt",
            user_id=user_id,
            success=success,
            ip_address=ip_address,
            user_agent=user_agent,
            event_data=event_data,
            error_message=error_message,
            session=session
        )

    @staticmethod
    async def log_registration_attempt(
        email: str,
        success: bool,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """Log registration attempt."""
        event_data = {"email": email}
        error_message = None

        if not success and failure_reason:
            error_message = failure_reason
            event_data["failure_reason"] = failure_reason

        await SecurityAuditService.log_authentication_event(
            event_type="registration_attempt",
            user_id=user_id,
            success=success,
            ip_address=ip_address,
            user_agent=user_agent,
            event_data=event_data,
            error_message=error_message,
            session=session
        )

    @staticmethod
    async def log_password_reset_request(
        email: str,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """Log password reset request."""
        await SecurityAuditService.log_account_event(
            event_type="password_reset_request",
            user_id=user_id,
            description=f"Password reset requested for {email}",
            event_data={"email": email},
            ip_address=ip_address,
            user_agent=user_agent,
            session=session
        )

    @staticmethod
    async def log_password_reset_completion(
        user_id: int,
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """Log password reset completion."""
        await SecurityAuditService.log_account_event(
            event_type="password_reset_completed",
            user_id=user_id,
            description="Password reset completed",
            success=success,
            severity="medium",
            ip_address=ip_address,
            user_agent=user_agent,
            session=session
        )

    @staticmethod
    async def log_email_verification(
        user_id: int,
        email: str,
        success: bool,
        ip_address: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """Log email verification attempt."""
        await SecurityAuditService.log_account_event(
            event_type="email_verification",
            user_id=user_id,
            description=f"Email verification for {email}",
            success=success,
            event_data={"email": email},
            ip_address=ip_address,
            session=session
        )

    @staticmethod
    async def log_suspicious_activity(
        event_type: str,
        description: str,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """Log suspicious activity."""
        await SecurityAuditService.log_security_event(
            event_type=event_type,
            description=description,
            user_id=user_id,
            severity="critical",
            event_data=event_data,
            ip_address=ip_address,
            user_agent=user_agent,
            session=session
        )