"""Symmetric encryption for stored SMTP passwords.

The key is derived from `settings.secret_key`, which is already required
for JWT signing — no extra env var to configure or lose. Rotating
SECRET_KEY therefore invalidates stored SMTP passwords; the user re-enters
the app password, which is a 30-second fix and the safer failure mode.
"""

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from ...config.settings import settings

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> Optional[str]:
    """Returns None if the token can't be decrypted (e.g. SECRET_KEY changed)."""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as e:
        logger.warning(f"Could not decrypt stored SMTP password: {e}")
        return None
