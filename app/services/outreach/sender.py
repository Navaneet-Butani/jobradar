"""Per-user SMTP sending, with optional resume attachment.

Deliberately separate from `app/services/email/smtp_client.py`: that one
sends *system* mail (digests, password resets) from one global address.
This one sends *as the user*, from the credentials they supplied, and is
the only path outreach ever takes.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Optional

from ...models import UserEmailAccountDB
from .crypto import decrypt_secret

logger = logging.getLogger(__name__)

SMTP_TIMEOUT = 30
DEFAULT_ATTACHMENT_NAME = "resume.pdf"


class OutreachSendError(Exception):
    """SMTP refused the message, or the account is unusable."""


def _guess_attachment_parts(filename: str) -> tuple[str, str]:
    name = (filename or DEFAULT_ATTACHMENT_NAME).lower()
    if name.endswith(".pdf"):
        return "application", "pdf"
    if name.endswith(".docx"):
        return "application", "vnd.openxmlformats-officedocument.wordprocessingml.document"
    if name.endswith((".txt", ".md")):
        return "text", "plain"
    return "application", "octet-stream"


def _build_message(
    account: UserEmailAccountDB,
    to_email: str,
    to_name: Optional[str],
    subject: str,
    body: str,
    attachment: Optional[tuple[str, bytes]] = None,
    in_reply_to: Optional[str] = None,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((account.from_name, account.from_email))
    message["To"] = formataddr((to_name, to_email)) if to_name else to_email
    message["Reply-To"] = account.from_email
    message["Message-ID"] = make_msgid()

    # A follow-up threads under the original in the recipient's client, which is
    # both the polite form and what makes their reply match back to step 1.
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to
    # Plain text only — a hand-written job enquiry that arrives as marketing
    # HTML reads as a blast and lands in Promotions.
    message.set_content(body)

    if attachment:
        filename, data = attachment
        maintype, subtype = _guess_attachment_parts(filename)
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    return message


def _send_sync(account: UserEmailAccountDB, password: str, message: EmailMessage) -> None:
    server = smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=SMTP_TIMEOUT)
    try:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(account.smtp_username, password)
        server.send_message(message)
    finally:
        try:
            server.quit()
        except Exception:
            pass


async def send_as_user(
    account: UserEmailAccountDB,
    to_email: str,
    subject: str,
    body: str,
    to_name: Optional[str] = None,
    attachment: Optional[tuple[str, bytes]] = None,
    in_reply_to: Optional[str] = None,
) -> str:
    """Send one email as the user and return its Message-ID.

    Raises OutreachSendError on any failure. No retry loop: a rejected
    outreach email is usually rejected for a reason that retrying makes worse
    (bad address, rate limit). The caller records the failure and moves on.
    """
    password = decrypt_secret(account.smtp_password_encrypted)
    if not password:
        raise OutreachSendError(
            "Stored email password could not be decrypted — re-enter it in Outreach settings."
        )

    message = _build_message(account, to_email, to_name, subject, body, attachment, in_reply_to)

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send_sync, account, password, message)
    except smtplib.SMTPAuthenticationError as e:
        raise OutreachSendError(
            "SMTP rejected the login. For Gmail you need a 16-character App Password "
            "with 2-Step Verification on — your normal account password will not work."
        ) from e
    except smtplib.SMTPRecipientsRefused as e:
        raise OutreachSendError(f"Recipient refused: {to_email}") from e
    except Exception as e:
        raise OutreachSendError(f"SMTP send failed: {e}") from e

    logger.info(f"Outreach email sent from {account.from_email} to {to_email}")
    return message["Message-ID"]


async def verify_account(account: UserEmailAccountDB) -> None:
    """Connect and log in without sending. Raises OutreachSendError if it fails."""
    password = decrypt_secret(account.smtp_password_encrypted)
    if not password:
        raise OutreachSendError("Stored email password could not be decrypted — re-enter it.")

    def _check() -> None:
        server = smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=SMTP_TIMEOUT)
        try:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(account.smtp_username, password)
        finally:
            try:
                server.quit()
            except Exception:
                pass

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _check)
    except smtplib.SMTPAuthenticationError as e:
        raise OutreachSendError(
            "Login rejected. Gmail needs a 16-character App Password (2-Step Verification on), "
            "not your account password."
        ) from e
    except Exception as e:
        raise OutreachSendError(f"Could not connect to {account.smtp_host}:{account.smtp_port} — {e}") from e
