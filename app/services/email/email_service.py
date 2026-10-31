"""Enhanced email service using Amazon SES and template system."""

import logging
from typing import Optional
from datetime import datetime, timedelta

from .resend_client import ResendEmailClient
from .ses_client import SESEmailClient
from .smtp_client import SMTPEmailClient
from .template_manager import EmailTemplateManager
from .queue import EmailQueue, EmailType, EmailPriority, get_email_queue
from ...config.settings import settings

logger = logging.getLogger(__name__)


TRANSPORTS = {
    "smtp": SMTPEmailClient,
    "resend": ResendEmailClient,
    "ses": SESEmailClient,
}


class EmailService:
    """System email — transport (smtp | resend | ses) picked via EMAIL_TRANSPORT.

    Outreach does NOT go through here; it sends from each user's own mailbox
    (`app/services/outreach/sender.py`) so replies and sending reputation stay
    with the person, not the app.
    """

    def __init__(self):
        """Initialize email service components."""
        transport = (settings.email_transport or "smtp").lower()
        client_class = TRANSPORTS.get(transport)
        if client_class is None:
            logger.warning(
                f"Unknown EMAIL_TRANSPORT '{transport}' — falling back to smtp. "
                f"Valid values: {', '.join(TRANSPORTS)}"
            )
            client_class = SMTPEmailClient
        self.mail_client = client_class()
        self.template_manager = EmailTemplateManager()
        self._queue = None

    async def get_queue(self) -> EmailQueue:
        """Get email queue instance."""
        if self._queue is None:
            self._queue = await get_email_queue()
        return self._queue

    async def send_welcome_email(
        self,
        user_email: str,
        user_name: str,
        activation_token: str
    ) -> bool:
        """
        Send welcome email to new user.

        Args:
            user_email: User's email address
            user_name: User's display name
            activation_token: Email verification token

        Returns:
            True if queued successfully
        """
        try:
            # Build activation link
            base_url = settings.frontend_url
            activation_link = f"{base_url}/verify-email?token={activation_token}"

            # Template context
            context = {
                "user_name": user_name,
                "recipient_email": user_email,
                "activation_link": activation_link,
                "verification_link": activation_link,  # Alias for template compatibility
            }

            # Queue email
            queue = await self.get_queue()
            email_id = await queue.enqueue_email(
                email_type=EmailType.WELCOME,
                recipient=user_email,
                subject=f"Welcome to {settings.ses_from_name}!",
                template_name="welcome",
                template_data=context,
                priority=EmailPriority.HIGH
            )

            logger.info(f"Welcome email queued for {user_email}, ID: {email_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to queue welcome email for {user_email}: {e}")
            return False

    async def send_verification_email(
        self,
        user_email: str,
        verification_token: str,
        user_name: Optional[str] = None
    ) -> bool:
        """
        Send email verification email.

        Args:
            user_email: User's email address
            verification_token: Email verification token
            user_name: User's display name

        Returns:
            True if queued successfully
        """
        try:
            # Build verification link
            base_url = settings.frontend_url
            verification_link = f"{base_url}/verify-email?token={verification_token}"

            # Template context
            display_name = user_name if user_name else user_email.split('@')[0]
            context = {
                "user_name": display_name,
                "recipient_email": user_email,
                "verification_link": verification_link,
            }

            # Queue email
            queue = await self.get_queue()
            email_id = await queue.enqueue_email(
                email_type=EmailType.VERIFICATION,
                recipient=user_email,
                subject=f"Verify Your {settings.ses_from_name} Email",
                template_name="email_verification",
                template_data=context,
                priority=EmailPriority.HIGH
            )

            logger.info(f"Verification email queued for {user_email}, ID: {email_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to queue verification email for {user_email}: {e}")
            return False

    async def send_password_reset_email(
        self,
        user_email: str,
        reset_token: str,
        user_name: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Send password reset email.

        Args:
            user_email: User's email address
            reset_token: Password reset token
            user_name: User's display name
            ip_address: IP address that requested reset

        Returns:
            True if queued successfully
        """
        try:
            # Build reset link
            base_url = settings.frontend_url
            reset_link = f"{base_url}/reset-password?token={reset_token}"

            # Calculate expiry time
            expiry_time = datetime.utcnow() + timedelta(hours=settings.password_reset_expire_hours)

            # Template context
            display_name = user_name if user_name else user_email.split('@')[0]
            context = {
                "user_name": display_name,
                "recipient_email": user_email,
                "reset_link": reset_link,
                "ip_address": ip_address,
                "expiry_time": expiry_time,
            }

            # Queue email
            queue = await self.get_queue()
            email_id = await queue.enqueue_email(
                email_type=EmailType.PASSWORD_RESET,
                recipient=user_email,
                subject=f"Reset Your {settings.ses_from_name} Password",
                template_name="password_reset",
                template_data=context,
                priority=EmailPriority.URGENT  # Security-related, high priority
            )

            logger.info(f"Password reset email queued for {user_email}, ID: {email_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to queue password reset email for {user_email}: {e}")
            return False

    async def send_password_changed_notification(
        self,
        user_email: str,
        user_name: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Send password change notification.

        Args:
            user_email: User's email address
            user_name: User's display name
            ip_address: IP address that changed password

        Returns:
            True if queued successfully
        """
        try:
            # Template context
            display_name = user_name if user_name else user_email.split('@')[0]
            context = {
                "user_name": display_name,
                "recipient_email": user_email,
                "ip_address": ip_address,
                "change_time": datetime.utcnow(),
            }

            # Queue email
            queue = await self.get_queue()
            email_id = await queue.enqueue_email(
                email_type=EmailType.PASSWORD_CHANGED,
                recipient=user_email,
                subject=f"Your {settings.ses_from_name} Password Has Been Changed",
                template_name="password_changed",
                template_data=context,
                priority=EmailPriority.URGENT  # Security notification
            )

            logger.info(f"Password changed notification queued for {user_email}, ID: {email_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to queue password changed notification for {user_email}: {e}")
            return False

    async def send_account_locked_notification(
        self,
        user_email: str,
        user_name: Optional[str] = None,
        lockout_duration: int = 15
    ) -> bool:
        """
        Send account lockout notification.

        Args:
            user_email: User's email address
            user_name: User's display name
            lockout_duration: Lockout duration in minutes

        Returns:
            True if queued successfully
        """
        try:
            # Template context
            display_name = user_name if user_name else user_email.split('@')[0]
            unlock_time = datetime.utcnow() + timedelta(minutes=lockout_duration)

            context = {
                "user_name": display_name,
                "recipient_email": user_email,
                "lockout_duration": lockout_duration,
                "unlock_time": unlock_time,
                "locked_at": datetime.utcnow(),
            }

            # Queue email
            queue = await self.get_queue()
            email_id = await queue.enqueue_email(
                email_type=EmailType.NOTIFICATION,
                recipient=user_email,
                subject=f"Your {settings.ses_from_name} Account Has Been Temporarily Locked",
                template_name="account_locked",
                template_data=context,
                priority=EmailPriority.URGENT  # Security notification
            )

            logger.info(f"Account locked notification queued for {user_email}, ID: {email_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to queue account locked notification for {user_email}: {e}")
            return False

    async def send_login_alert(
        self,
        user_email: str,
        user_name: Optional[str] = None,
        ip_address: Optional[str] = None,
        device_info: Optional[str] = None,
        location: Optional[str] = None
    ) -> bool:
        """
        Send login alert for suspicious activity.

        Args:
            user_email: User's email address
            user_name: User's display name
            ip_address: Login IP address
            device_info: Device/browser information
            location: Geographic location (if available)

        Returns:
            True if queued successfully
        """
        try:
            # Template context
            display_name = user_name if user_name else user_email.split('@')[0]
            context = {
                "user_name": display_name,
                "recipient_email": user_email,
                "ip_address": ip_address,
                "device_info": device_info,
                "location": location,
                "login_time": datetime.utcnow(),
            }

            # Queue email
            queue = await self.get_queue()
            email_id = await queue.enqueue_email(
                email_type=EmailType.NOTIFICATION,
                recipient=user_email,
                subject=f"New Login to Your {settings.ses_from_name} Account",
                template_name="login_alert",
                template_data=context,
                priority=EmailPriority.URGENT  # Security notification
            )

            logger.info(f"Login alert queued for {user_email}, ID: {email_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to queue login alert for {user_email}: {e}")
            return False

    async def send_direct_email(
        self,
        to_email: str,
        subject: str,
        template_name: str,
        template_data: dict,
        priority: EmailPriority = EmailPriority.NORMAL
    ) -> bool:
        """
        Send email directly (bypass queue) for urgent messages.

        Args:
            to_email: Recipient email
            subject: Email subject
            template_name: Template to use
            template_data: Template context data
            priority: Email priority (for logging)

        Returns:
            True if sent successfully
        """
        try:
            # Render template
            html_content, text_content = await self.template_manager.render_template(
                template_name,
                template_data
            )

            # Send directly via SES
            message_id = await self.mail_client.send_email(
                to_email=to_email,
                subject=subject,
                html_body=html_content,
                text_body=text_content
            )

            if message_id:
                logger.info(f"Direct email sent to {to_email}, MessageID: {message_id}")
                return True
            else:
                logger.error(f"Failed to send direct email to {to_email}")
                return False

        except Exception as e:
            logger.error(f"Failed to send direct email to {to_email}: {e}")
            return False

    @staticmethod
    def is_email_configured() -> bool:
        """Check if email service is properly configured for the selected transport."""
        transport = (settings.email_transport or "smtp").lower()
        if transport == "smtp":
            return bool(settings.smtp_host and settings.smtp_username and settings.smtp_password)
        if transport == "resend":
            return bool(settings.resend_api_key and settings.ses_from_email)
        return (
            bool(settings.aws_access_key_id) and
            bool(settings.aws_secret_access_key) and
            bool(settings.ses_from_email)
        )

    async def health_check(self) -> dict:
        """
        Perform email service health check.

        Returns:
            Health status dictionary
        """
        health = {
            "configured": self.is_email_configured(),
            "transport": settings.email_transport,
            "transport_healthy": False,
            "queue_healthy": False,
            "template_system": False
        }

        try:
            health["transport_healthy"] = await self.mail_client.health_check()

            # Check queue health
            queue = await self.get_queue()
            stats = await queue.get_queue_stats()
            health["queue_healthy"] = isinstance(stats, dict)
            health["queue_stats"] = stats

            # Check template system
            templates = self.template_manager.get_template_list()
            health["template_system"] = len(templates) > 0
            health["available_templates"] = templates

            # Overall health
            health["healthy"] = all([
                health["configured"],
                health["transport_healthy"],
                health["queue_healthy"],
                health["template_system"]
            ])

        except Exception as e:
            logger.error(f"Email service health check failed: {e}")
            health["error"] = str(e)

        return health


# Global email service instance
_email_service = None


def get_email_service() -> EmailService:
    """Get global email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service