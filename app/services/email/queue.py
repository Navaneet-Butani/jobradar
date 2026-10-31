"""Email queue system using Redis for asynchronous email processing."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

import redis.asyncio as redis
from tenacity import retry, stop_after_attempt, wait_exponential

from ...config.settings import settings
from ...core.redis import get_redis

logger = logging.getLogger(__name__)


class EmailType(str, Enum):
    """Email types for categorization."""
    WELCOME = "welcome"
    VERIFICATION = "verification"
    PASSWORD_RESET = "password_reset"
    PASSWORD_CHANGED = "password_changed"
    JOB_ALERT = "job_alert"
    WEEKLY_DIGEST = "weekly_digest"
    NOTIFICATION = "notification"


class EmailPriority(int, Enum):
    """Email priority levels."""
    URGENT = 1      # Security alerts, password resets
    HIGH = 3        # Email verification, account notifications
    NORMAL = 5      # Welcome emails, general notifications
    LOW = 7         # Job alerts, marketing emails
    BULK = 9        # Weekly digests, bulk notifications


class EmailStatus(str, Enum):
    """Email processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    RETRY = "retry"
    DEAD = "dead"


@dataclass
class EmailData:
    """Email data structure for queue."""
    id: str
    type: EmailType
    recipient: str
    subject: str
    template_name: str
    template_data: Dict[str, Any]
    priority: EmailPriority
    attempts: int = 0
    max_attempts: int = 3
    status: EmailStatus = EmailStatus.PENDING
    created_at: datetime = None
    scheduled_for: datetime = None
    retry_after: Optional[datetime] = None
    message_id: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.scheduled_for is None:
            self.scheduled_for = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat() if value else None
            elif isinstance(value, (EmailType, EmailPriority, EmailStatus)):
                data[key] = value.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmailData':
        """Create instance from dictionary."""
        # Convert ISO strings back to datetime objects
        datetime_fields = ['created_at', 'scheduled_for', 'retry_after']
        for field in datetime_fields:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])

        # Convert enum strings back to enums
        if 'type' in data:
            data['type'] = EmailType(data['type'])
        if 'priority' in data:
            data['priority'] = EmailPriority(data['priority'])
        if 'status' in data:
            data['status'] = EmailStatus(data['status'])

        return cls(**data)


class EmailQueue:
    """Redis-based email queue for asynchronous processing."""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize email queue."""
        self.redis = redis_client or get_redis()
        self.queue_prefix = "email_queue"
        self.processing_set = f"{self.queue_prefix}:processing"
        self.dead_letter_queue = f"{self.queue_prefix}:dead"
        self.stats_key = f"{self.queue_prefix}:stats"

        # Queue names by priority
        self.priority_queues = {
            EmailPriority.URGENT: f"{self.queue_prefix}:urgent",
            EmailPriority.HIGH: f"{self.queue_prefix}:high",
            EmailPriority.NORMAL: f"{self.queue_prefix}:normal",
            EmailPriority.LOW: f"{self.queue_prefix}:low",
            EmailPriority.BULK: f"{self.queue_prefix}:bulk",
        }

    async def enqueue_email(
        self,
        email_type: EmailType,
        recipient: str,
        subject: str,
        template_name: str,
        template_data: Dict[str, Any],
        priority: EmailPriority = EmailPriority.NORMAL,
        scheduled_for: Optional[datetime] = None
    ) -> str:
        """
        Add email to queue.

        Args:
            email_type: Type of email
            recipient: Recipient email address
            subject: Email subject
            template_name: Name of email template
            template_data: Template context data
            priority: Email priority level
            scheduled_for: When to send email (default: now)

        Returns:
            Email ID
        """
        try:
            email_id = str(uuid.uuid4())

            email_data = EmailData(
                id=email_id,
                type=email_type,
                recipient=recipient,
                subject=subject,
                template_name=template_name,
                template_data=template_data,
                priority=priority,
                scheduled_for=scheduled_for or datetime.utcnow()
            )

            # Store email data
            await self.redis.hset(
                f"{self.queue_prefix}:emails",
                email_id,
                json.dumps(email_data.to_dict(), default=str)
            )

            # Add to priority queue
            queue_name = self.priority_queues[priority]
            score = email_data.scheduled_for.timestamp()
            await self.redis.zadd(queue_name, {email_id: score})

            # Update stats
            await self._update_stats("enqueued", email_type.value)

            logger.info(f"Email queued: {email_id} ({email_type.value}) to {recipient}")
            return email_id

        except Exception as e:
            logger.error(f"Failed to enqueue email: {e}")
            raise

    async def dequeue_email(self, timeout: int = 10) -> Optional[EmailData]:
        """
        Dequeue next email for processing.

        Args:
            timeout: Timeout in seconds

        Returns:
            EmailData if available, None if timeout
        """
        try:
            current_time = datetime.utcnow().timestamp()

            # Check queues in priority order
            for priority in EmailPriority:
                queue_name = self.priority_queues[priority]

                # Get emails scheduled for now or earlier
                results = await self.redis.zrangebyscore(
                    queue_name, 0, current_time, start=0, num=1, withscores=True
                )

                if results:
                    email_id = results[0][0].decode()

                    # Remove from queue
                    await self.redis.zrem(queue_name, email_id)

                    # Get email data
                    email_json = await self.redis.hget(f"{self.queue_prefix}:emails", email_id)
                    if email_json:
                        email_data = EmailData.from_dict(json.loads(email_json))

                        # Mark as processing
                        email_data.status = EmailStatus.PROCESSING
                        await self._update_email_data(email_data)

                        # Add to processing set
                        await self.redis.sadd(self.processing_set, email_id)

                        logger.debug(f"Dequeued email: {email_id}")
                        return email_data

            return None

        except Exception as e:
            logger.error(f"Failed to dequeue email: {e}")
            return None

    async def mark_sent(self, email_id: str, message_id: str):
        """Mark email as successfully sent."""
        try:
            email_data = await self._get_email_data(email_id)
            if email_data:
                email_data.status = EmailStatus.SENT
                email_data.message_id = message_id
                await self._update_email_data(email_data)

                # Remove from processing set
                await self.redis.srem(self.processing_set, email_id)

                # Update stats
                await self._update_stats("sent", email_data.type.value)

                logger.info(f"Email marked as sent: {email_id}")

        except Exception as e:
            logger.error(f"Failed to mark email as sent: {e}")

    async def mark_failed(self, email_id: str, error_message: str):
        """Mark email as failed and handle retry logic."""
        try:
            email_data = await self._get_email_data(email_id)
            if not email_data:
                return

            email_data.attempts += 1
            email_data.error_message = error_message

            if email_data.attempts < email_data.max_attempts:
                # Schedule retry with exponential backoff
                retry_delay = min(300, 30 * (2 ** (email_data.attempts - 1)))  # Max 5 minutes
                email_data.retry_after = datetime.utcnow() + timedelta(seconds=retry_delay)
                email_data.scheduled_for = email_data.retry_after
                email_data.status = EmailStatus.RETRY

                # Re-queue for retry
                queue_name = self.priority_queues[email_data.priority]
                score = email_data.scheduled_for.timestamp()
                await self.redis.zadd(queue_name, {email_id: score})

                logger.warning(f"Email scheduled for retry {email_data.attempts}/{email_data.max_attempts}: {email_id}")

            else:
                # Move to dead letter queue
                email_data.status = EmailStatus.DEAD
                await self.redis.lpush(self.dead_letter_queue, email_id)

                # Update stats
                await self._update_stats("dead", email_data.type.value)

                logger.error(f"Email moved to dead letter queue: {email_id}")

            await self._update_email_data(email_data)

            # Remove from processing set
            await self.redis.srem(self.processing_set, email_id)

            # Update stats
            await self._update_stats("failed", email_data.type.value)

        except Exception as e:
            logger.error(f"Failed to mark email as failed: {e}")

    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        try:
            stats = {}

            # Count emails in each priority queue
            for priority, queue_name in self.priority_queues.items():
                count = await self.redis.zcard(queue_name)
                stats[f"{priority.name.lower()}_pending"] = count

            # Processing count
            stats["processing"] = await self.redis.scard(self.processing_set)

            # Dead letter queue count
            stats["dead"] = await self.redis.llen(self.dead_letter_queue)

            # Daily stats
            daily_stats = await self.redis.hgetall(f"{self.stats_key}:daily:{datetime.utcnow().strftime('%Y-%m-%d')}")
            stats["daily"] = {k.decode(): int(v) for k, v in daily_stats.items()}

            return stats

        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {}

    async def clear_queue(self, queue_type: str = "all"):
        """Clear queue data (admin function)."""
        try:
            if queue_type == "all":
                # Clear all queues
                for queue_name in self.priority_queues.values():
                    await self.redis.delete(queue_name)
                await self.redis.delete(self.processing_set)
                await self.redis.delete(f"{self.queue_prefix}:emails")
                logger.info("All queues cleared")

            elif queue_type == "dead":
                await self.redis.delete(self.dead_letter_queue)
                logger.info("Dead letter queue cleared")

        except Exception as e:
            logger.error(f"Failed to clear queue: {e}")

    async def requeue_dead_emails(self, limit: int = 100) -> int:
        """Requeue emails from dead letter queue."""
        try:
            requeued = 0
            for _ in range(limit):
                email_id = await self.redis.rpop(self.dead_letter_queue)
                if not email_id:
                    break

                email_id = email_id.decode()
                email_data = await self._get_email_data(email_id)
                if email_data:
                    # Reset for retry
                    email_data.attempts = 0
                    email_data.status = EmailStatus.PENDING
                    email_data.scheduled_for = datetime.utcnow()
                    email_data.error_message = None

                    # Re-queue
                    queue_name = self.priority_queues[email_data.priority]
                    score = email_data.scheduled_for.timestamp()
                    await self.redis.zadd(queue_name, {email_id: score})

                    await self._update_email_data(email_data)
                    requeued += 1

            logger.info(f"Requeued {requeued} emails from dead letter queue")
            return requeued

        except Exception as e:
            logger.error(f"Failed to requeue dead emails: {e}")
            return 0

    async def _get_email_data(self, email_id: str) -> Optional[EmailData]:
        """Get email data from Redis."""
        try:
            email_json = await self.redis.hget(f"{self.queue_prefix}:emails", email_id)
            if email_json:
                return EmailData.from_dict(json.loads(email_json))
            return None
        except Exception as e:
            logger.error(f"Failed to get email data for {email_id}: {e}")
            return None

    async def _update_email_data(self, email_data: EmailData):
        """Update email data in Redis."""
        try:
            await self.redis.hset(
                f"{self.queue_prefix}:emails",
                email_data.id,
                json.dumps(email_data.to_dict(), default=str)
            )
        except Exception as e:
            logger.error(f"Failed to update email data: {e}")

    async def _update_stats(self, action: str, email_type: str):
        """Update daily statistics."""
        try:
            today = datetime.utcnow().strftime('%Y-%m-%d')
            stats_key = f"{self.stats_key}:daily:{today}"

            await self.redis.hincrby(stats_key, f"{action}_total", 1)
            await self.redis.hincrby(stats_key, f"{action}_{email_type}", 1)

            # Set expiration for stats (30 days)
            await self.redis.expire(stats_key, 30 * 24 * 3600)

        except Exception as e:
            logger.error(f"Failed to update stats: {e}")


class EmailWorker:
    """Background worker for processing email queue."""

    def __init__(self, queue: EmailQueue, ses_client, template_manager):
        """Initialize email worker."""
        self.queue = queue
        self.ses_client = ses_client
        self.template_manager = template_manager
        self.running = False
        self.rate_limiter = asyncio.Semaphore(settings.email_queue_rate_limit)

    async def start(self):
        """Start the email worker."""
        self.running = True
        logger.info("Email worker started")

        try:
            while self.running:
                await self._process_emails()
                await asyncio.sleep(1)  # Short sleep to prevent busy waiting
        except Exception as e:
            logger.error(f"Email worker error: {e}")
        finally:
            logger.info("Email worker stopped")

    async def stop(self):
        """Stop the email worker."""
        self.running = False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def _process_emails(self):
        """Process emails from queue."""
        try:
            email_data = await self.queue.dequeue_email(timeout=5)
            if not email_data:
                return

            async with self.rate_limiter:
                await self._send_email(email_data)

        except Exception as e:
            logger.error(f"Error processing emails: {e}")

    async def _send_email(self, email_data: EmailData):
        """Send individual email."""
        try:
            # Render template
            html_content, text_content = await self.template_manager.render_template(
                email_data.template_name,
                email_data.template_data
            )

            # Send via SES
            message_id = await self.ses_client.send_email(
                to_email=email_data.recipient,
                subject=email_data.subject,
                html_body=html_content,
                text_body=text_content
            )

            if message_id:
                await self.queue.mark_sent(email_data.id, message_id)
                logger.info(f"Email sent successfully: {email_data.id} -> {email_data.recipient}")
            else:
                await self.queue.mark_failed(email_data.id, "Failed to send via SES")

        except Exception as e:
            error_msg = f"Email sending failed: {str(e)}"
            await self.queue.mark_failed(email_data.id, error_msg)
            logger.error(f"Failed to send email {email_data.id}: {e}")


# Global email queue instance
_email_queue = None


async def get_email_queue() -> EmailQueue:
    """Get global email queue instance."""
    global _email_queue
    if _email_queue is None:
        _email_queue = EmailQueue()
    return _email_queue