"""Read replies and bounces back out of the sender's own mailbox.

There is no open tracking here on purpose. An open pixel needs HTML mail
and a public URL, and Gmail's image proxy pre-fetches it — so the number
it produces is a number, but not a fact. A reply is a fact.

Matching works off the RFC Message-ID we stamped on each outgoing email:
  - a reply carries it in `In-Reply-To` or somewhere in `References`
  - a bounce carries it inside the attached original headers

Both are found by scanning recent INBOX messages; nothing is ever deleted,
moved, or marked read.
"""

import email
import imaplib
import logging
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

from ...models import UserEmailAccountDB
from .crypto import decrypt_secret

logger = logging.getLogger(__name__)

IMAP_TIMEOUT = 45
DEFAULT_LOOKBACK_DAYS = 30
MAX_MESSAGES_PER_SYNC = 500
SNIPPET_CHARS = 400

MESSAGE_ID_RE = re.compile(r"<[^<>@\s]+@[^<>\s]+>")

BOUNCE_SENDERS = (
    "mailer-daemon",
    "postmaster",
    "mail-daemon",
    "no-reply-delivery",
)
BOUNCE_SUBJECT_HINTS = (
    "undeliverable",
    "delivery status notification",
    "returned mail",
    "delivery has failed",
    "failure notice",
    "mail delivery failed",
    "address not found",
)


class InboxSyncError(Exception):
    """IMAP refused the connection or the login."""


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _body_text(message: email.message.Message) -> str:
    """Best-effort plain text of a message, including bounce attachments."""
    chunks: list[str] = []
    for part in message.walk():
        content_type = part.get_content_type()
        if content_type in ("text/plain", "message/rfc822", "text/rfc822-headers", "message/delivery-status"):
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    chunks.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
                else:
                    chunks.append(str(part.get_payload()))
            except Exception:
                continue
    return "\n".join(chunks)


def _referenced_message_ids(message: email.message.Message, body: str) -> set[str]:
    """Every Message-ID this mail points at — headers first, then the body."""
    found: set[str] = set()
    for header in ("In-Reply-To", "References"):
        found.update(MESSAGE_ID_RE.findall(message.get(header, "") or ""))
    # Bounces quote the original headers rather than setting In-Reply-To.
    found.update(MESSAGE_ID_RE.findall(body))
    return found


def _is_bounce(message: email.message.Message) -> bool:
    sender = (message.get("From", "") or "").lower()
    subject = _decode(message.get("Subject")).lower()
    if any(marker in sender for marker in BOUNCE_SENDERS):
        return True
    if any(hint in subject for hint in BOUNCE_SUBJECT_HINTS):
        return True
    return message.get_content_type() == "multipart/report"


def _bounce_reason(body: str) -> str:
    """Pull the human-readable line out of a DSN, falling back to its first lines."""
    for pattern in (
        r"(?im)^\s*(?:Diagnostic-Code|Status):\s*(.+)$",
        r"(?im)^.*\b(5\d\d[- ]\d\.\d\.\d)\b.*$",
        r"(?im)^.*(address not found|does not exist|user unknown|mailbox unavailable|blocked).*$",
    ):
        match = re.search(pattern, body)
        if match:
            return match.group(0).strip()[:500]
    return " ".join(body.split())[:500] or "Delivery failed (no reason given)"


def _received_at(message: email.message.Message) -> datetime:
    try:
        parsed = parsedate_to_datetime(message.get("Date"))
        if parsed is None:
            return datetime.utcnow()
        return parsed.astimezone(tz=None).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def _snippet(body: str) -> str:
    """Strip quoted history so the snippet shows what they actually wrote."""
    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if re.match(r"(?i)^on .{10,80}\bwrote:$", stripped):
            break
        if stripped.startswith("--") and len(stripped) <= 4:
            break
        lines.append(stripped)
    return " ".join(" ".join(lines).split())[:SNIPPET_CHARS]


def _connect(account: UserEmailAccountDB) -> imaplib.IMAP4_SSL:
    password = decrypt_secret(account.smtp_password_encrypted)
    if not password:
        raise InboxSyncError("Stored email password could not be decrypted — re-enter it in Outreach settings.")

    try:
        client = imaplib.IMAP4_SSL(account.imap_host, account.imap_port, timeout=IMAP_TIMEOUT)
    except Exception as e:
        raise InboxSyncError(f"Could not reach {account.imap_host}:{account.imap_port} — {e}") from e

    try:
        client.login(account.smtp_username, password)
    except imaplib.IMAP4.error as e:
        try:
            client.logout()
        except Exception:
            pass
        raise InboxSyncError(
            "IMAP login was rejected. The same Gmail App Password should work — check that IMAP "
            f"is enabled for {account.smtp_username} in Gmail settings. ({e})"
        ) from e

    return client


def fetch_feedback(account: UserEmailAccountDB, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict:
    """Scan recent INBOX mail. Returns {message_id: {...}} keyed by OUR sent Message-ID.

    Blocking (imaplib has no async API) — call it from a thread executor.
    """
    since = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%d-%b-%Y")
    feedback: dict[str, dict] = {}

    client = _connect(account)
    try:
        client.select("INBOX", readonly=True)
        status, data = client.search(None, "SINCE", since)
        if status != "OK":
            raise InboxSyncError(f"IMAP search failed: {status}")

        uids = (data[0] or b"").split()
        # Newest first, so a capped scan keeps the most relevant window.
        uids = uids[-MAX_MESSAGES_PER_SYNC:]

        for uid in reversed(uids):
            status, payload = client.fetch(uid, "(BODY.PEEK[])")
            if status != "OK" or not payload or not isinstance(payload[0], tuple):
                continue

            try:
                message = email.message_from_bytes(payload[0][1])
            except Exception:
                continue

            body = _body_text(message)
            referenced = _referenced_message_ids(message, body)
            if not referenced:
                continue

            bounce = _is_bounce(message)
            for message_id in referenced:
                # Keep the first (newest) verdict we see for a given send.
                if message_id in feedback:
                    continue
                feedback[message_id] = {
                    "kind": "bounce" if bounce else "reply",
                    "at": _received_at(message),
                    "from": parseaddr(message.get("From", ""))[1].lower(),
                    "subject": _decode(message.get("Subject")),
                    "detail": _bounce_reason(body) if bounce else _snippet(body),
                }
    finally:
        try:
            client.close()
        except Exception:
            pass
        try:
            client.logout()
        except Exception:
            pass

    return feedback


def verify_imap(account: UserEmailAccountDB) -> None:
    """Log in and out without reading anything. Raises InboxSyncError on failure."""
    client = _connect(account)
    try:
        client.select("INBOX", readonly=True)
    finally:
        try:
            client.logout()
        except Exception:
            pass
