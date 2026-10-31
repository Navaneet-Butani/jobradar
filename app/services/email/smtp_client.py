"""SMTP email client — the ₹0/month transport until Resend/SES is wired up.

Same public surface as SESEmailClient (send_email, health_check,
is_configured) so EmailService can use either without callers changing.
"""

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from uuid import uuid4

from tenacity import retry, stop_after_attempt, wait_exponential

from ...config.settings import settings

logger = logging.getLogger(__name__)


class SMTPEmailClient:
    """Sends mail through a plain SMTP server (Gmail, Zoho, etc.) via smtplib."""

    def is_configured(self) -> bool:
        return bool(settings.smtp_host and settings.smtp_username and settings.smtp_password)

    async def health_check(self) -> bool:
        if not self.is_configured():
            return False
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._connect_and_login)
            return True
        except Exception as e:
            logger.error(f"SMTP health check failed: {e}")
            return False

    def _connect_and_login(self) -> smtplib.SMTP:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
        if settings.smtp_use_tls:
            server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        return server

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> Optional[str]:
        """Send a single email via SMTP. Returns a synthetic message id, or None on failure."""
        if not self.is_configured():
            logger.warning(f"SMTP not configured — dropping email to {to_email}")
            return None

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._send_sync, to_email, subject, html_body, text_body, reply_to
            )
            message_id = str(uuid4())
            logger.info(f"Email sent via SMTP to {to_email}, id: {message_id}")
            return message_id
        except Exception as e:
            logger.error(f"SMTP error sending to {to_email}: {e}")
            raise  # let tenacity retry; caller sees None only after retries are exhausted

    def _send_sync(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str],
        reply_to: Optional[str],
    ) -> None:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{settings.ses_from_name} <{settings.ses_from_email}>"
        message["To"] = to_email
        if reply_to:
            message["Reply-To"] = reply_to

        if text_body:
            message.attach(MIMEText(text_body, "plain"))
        message.attach(MIMEText(html_body, "html"))

        server = self._connect_and_login()
        try:
            server.sendmail(settings.ses_from_email, [to_email], message.as_string())
        finally:
            server.quit()
