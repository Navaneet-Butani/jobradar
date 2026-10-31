"""Email services package for JobFlow."""

from .ses_client import SESEmailClient, EmailRecipient, BulkSendResult
from .template_manager import EmailTemplateManager
from .queue import EmailQueue, EmailType, EmailPriority, EmailStatus, EmailData, EmailWorker, get_email_queue
from .email_service import EmailService, get_email_service

__all__ = [
    # SES Client
    "SESEmailClient",
    "EmailRecipient",
    "BulkSendResult",

    # Template System
    "EmailTemplateManager",

    # Queue System
    "EmailQueue",
    "EmailType",
    "EmailPriority",
    "EmailStatus",
    "EmailData",
    "EmailWorker",
    "get_email_queue",

    # Main Service
    "EmailService",
    "get_email_service",
]