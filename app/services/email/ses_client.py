"""Amazon SES email client for JobFlow."""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from tenacity import retry, stop_after_attempt, wait_exponential

from ...config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class EmailRecipient:
    """Email recipient data structure."""
    email: str
    name: Optional[str] = None


@dataclass
class BulkSendResult:
    """Result of bulk email sending operation."""
    total_sent: int
    total_failed: int
    successful_emails: List[str]
    failed_emails: List[Dict[str, Any]]
    message_ids: List[str]


class SESEmailClient:
    """Amazon SES email client with async support and rate limiting."""

    def __init__(self):
        """Initialize SES client with configuration."""
        self._ses_client = None
        self._rate_limiter = asyncio.Semaphore(settings.ses_rate_limit)
        self._last_send_time = 0
        self._send_quota = None
        self._send_rate = None

    @property
    def ses_client(self):
        """Get or create SES client instance."""
        if self._ses_client is None:
            if not settings.aws_access_key_id or not settings.aws_secret_access_key:
                raise ValueError("AWS credentials not configured for SES")

            self._ses_client = boto3.client(
                'ses',
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key
            )
        return self._ses_client

    async def health_check(self) -> bool:
        """Check SES service health and connectivity."""
        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.ses_client.get_send_quota
            )
            logger.info("SES health check successful")
            return True
        except Exception as e:
            logger.error(f"SES health check failed: {e}")
            return False

    async def get_send_quota(self) -> Dict[str, float]:
        """Get current SES sending quota and rate."""
        try:
            loop = asyncio.get_event_loop()
            quota_data = await loop.run_in_executor(
                None,
                self.ses_client.get_send_quota
            )

            self._send_quota = quota_data.get('Max24HourSend', 0)
            self._send_rate = quota_data.get('MaxSendRate', 0)

            return {
                'max_24_hour_send': quota_data.get('Max24HourSend', 0),
                'max_send_rate': quota_data.get('MaxSendRate', 0),
                'sent_last_24_hours': quota_data.get('SentLast24Hours', 0)
            }
        except Exception as e:
            logger.error(f"Failed to get SES quota: {e}")
            return {}

    async def _rate_limit(self):
        """Apply rate limiting for SES sends."""
        async with self._rate_limiter:
            current_time = asyncio.get_event_loop().time()
            time_since_last = current_time - self._last_send_time
            min_interval = 1.0 / settings.ses_rate_limit

            if time_since_last < min_interval:
                await asyncio.sleep(min_interval - time_since_last)

            self._last_send_time = asyncio.get_event_loop().time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> Optional[str]:
        """
        Send a single email via Amazon SES.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email content
            text_body: Plain text email content (optional)
            reply_to: Reply-to email address (optional)

        Returns:
            Message ID if successful, None if failed
        """
        try:
            await self._rate_limit()

            # Prepare message
            message = {
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {
                    'Html': {'Data': html_body, 'Charset': 'UTF-8'}
                }
            }

            if text_body:
                message['Body']['Text'] = {'Data': text_body, 'Charset': 'UTF-8'}

            # Prepare destination
            destination = {'ToAddresses': [to_email]}

            # Prepare source
            source = f"{settings.ses_from_name} <{settings.ses_from_email}>"

            # Optional reply-to
            kwargs = {}
            if reply_to:
                kwargs['ReplyToAddresses'] = [reply_to]

            # Send email
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.ses_client.send_email(
                    Source=source,
                    Destination=destination,
                    Message=message,
                    **kwargs
                )
            )

            message_id = response['MessageId']
            logger.info(f"Email sent successfully to {to_email}, MessageID: {message_id}")
            return message_id

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            if error_code in ['Throttling', 'SendingPausedException']:
                logger.warning(f"SES rate limiting or paused: {error_message}")
                raise  # Will trigger retry
            elif error_code in ['MessageRejected', 'MailFromDomainNotVerifiedException']:
                logger.error(f"SES configuration error: {error_message}")
                return None
            else:
                logger.error(f"SES error sending to {to_email}: {error_code} - {error_message}")
                return None

        except Exception as e:
            logger.error(f"Unexpected error sending email to {to_email}: {e}")
            return None

    async def send_bulk_emails(
        self,
        recipients: List[EmailRecipient],
        template_name: str,
        template_data: Dict[str, Any],
        max_batch_size: int = 50
    ) -> BulkSendResult:
        """
        Send bulk emails using SES templates (placeholder for template implementation).

        Args:
            recipients: List of email recipients
            template_name: SES template name
            template_data: Template variable data
            max_batch_size: Maximum emails per batch (SES limit is 50)

        Returns:
            BulkSendResult with success/failure statistics
        """
        result = BulkSendResult(
            total_sent=0,
            total_failed=0,
            successful_emails=[],
            failed_emails=[],
            message_ids=[]
        )

        # Process in batches
        for i in range(0, len(recipients), max_batch_size):
            batch = recipients[i:i + max_batch_size]
            batch_result = await self._send_bulk_batch(batch, template_name, template_data)

            result.total_sent += batch_result.total_sent
            result.total_failed += batch_result.total_failed
            result.successful_emails.extend(batch_result.successful_emails)
            result.failed_emails.extend(batch_result.failed_emails)
            result.message_ids.extend(batch_result.message_ids)

        logger.info(f"Bulk email complete: {result.total_sent} sent, {result.total_failed} failed")
        return result

    async def _send_bulk_batch(
        self,
        recipients: List[EmailRecipient],
        template_name: str,
        template_data: Dict[str, Any]
    ) -> BulkSendResult:
        """Send a single batch of bulk emails."""
        # This is a placeholder - actual implementation would use SES templates
        # For now, we'll send individual emails
        result = BulkSendResult(
            total_sent=0,
            total_failed=0,
            successful_emails=[],
            failed_emails=[],
            message_ids=[]
        )

        for recipient in recipients:
            try:
                # This would use actual template rendering in full implementation
                subject = f"JobFlow Notification"
                html_body = f"<html><body><h1>Hello {recipient.name or recipient.email}!</h1></body></html>"

                message_id = await self.send_email(
                    to_email=recipient.email,
                    subject=subject,
                    html_body=html_body
                )

                if message_id:
                    result.total_sent += 1
                    result.successful_emails.append(recipient.email)
                    result.message_ids.append(message_id)
                else:
                    result.total_failed += 1
                    result.failed_emails.append({
                        'email': recipient.email,
                        'error': 'Send failed'
                    })

            except Exception as e:
                result.total_failed += 1
                result.failed_emails.append({
                    'email': recipient.email,
                    'error': str(e)
                })

        return result

    async def verify_email_identity(self, email: str) -> bool:
        """
        Verify an email identity with SES.

        Args:
            email: Email address to verify

        Returns:
            True if verification was initiated successfully
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.ses_client.verify_email_identity(EmailAddress=email)
            )
            logger.info(f"Email verification initiated for {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to verify email identity {email}: {e}")
            return False

    async def get_verification_status(self, email: str) -> str:
        """
        Get verification status for an email identity.

        Args:
            email: Email address to check

        Returns:
            Verification status ('Success', 'Pending', 'Failed', or 'NotStarted')
        """
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.ses_client.get_identity_verification_attributes(
                    Identities=[email]
                )
            )

            attributes = response.get('VerificationAttributes', {})
            if email in attributes:
                return attributes[email].get('VerificationStatus', 'NotStarted')
            return 'NotStarted'

        except Exception as e:
            logger.error(f"Failed to get verification status for {email}: {e}")
            return 'Failed'

    def is_configured(self) -> bool:
        """Check if SES is properly configured."""
        return bool(
            settings.aws_access_key_id and
            settings.aws_secret_access_key and
            settings.ses_from_email
        )