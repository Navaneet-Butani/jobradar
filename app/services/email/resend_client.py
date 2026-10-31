"""Resend transport — the ₹0/month option the plan specifies for system mail.

Same public surface as SESEmailClient and SMTPEmailClient (`send_email`,
`health_check`, `is_configured`) so `EmailService` can swap between them on
`EMAIL_TRANSPORT` with no other change.

Free tier is ~100 emails/day, 3,000/month — comfortably above a small group's
digests. Plain HTTP via httpx; no SDK dependency needed for one endpoint.

Note this is *system* mail only (digests, password resets). Outreach never
goes through here — it sends from each user's own mailbox, see
`app/services/outreach/sender.py`.
"""

import logging
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from ...config.settings import settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
TIMEOUT = 20.0


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


class ResendEmailClient:
    """Sends mail through Resend's HTTP API."""

    def is_configured(self) -> bool:
        return bool(settings.resend_api_key and settings.ses_from_email)

    async def health_check(self) -> bool:
        """Resend has no ping endpoint; a configured key is as far as we can check cheaply."""
        return self.is_configured()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    async def _post(self, payload: dict) -> httpx.Response:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                RESEND_URL,
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return response

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> Optional[str]:
        """Send one email. Returns Resend's message id, or None on failure."""
        if not self.is_configured():
            logger.warning(f"Resend not configured — dropping email to {to_email}")
            return None

        payload = {
            "from": f"{settings.ses_from_name} <{settings.ses_from_email}>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }
        if text_body:
            payload["text"] = text_body
        if reply_to:
            payload["reply_to"] = reply_to

        try:
            response = await self._post(payload)
            message_id = response.json().get("id")
            logger.info(f"Email sent via Resend to {to_email}, id: {message_id}")
            return message_id
        except httpx.HTTPStatusError as e:
            # Resend puts the actionable reason in the body — usually an
            # unverified sending domain on a fresh account.
            detail = ""
            try:
                detail = e.response.json().get("message", "")
            except Exception:
                detail = e.response.text[:200]
            logger.error(f"Resend rejected the email to {to_email}: {e.response.status_code} {detail}")
            return None
        except Exception as e:
            logger.error(f"Resend error sending to {to_email}: {e}")
            return None
