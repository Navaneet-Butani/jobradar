"""Apply mailbox feedback to sent messages, then queue any follow-ups it unblocks.

Order matters: sync replies and bounces *first*, then decide follow-ups. A
follow-up sent to someone who already replied is the single worst mistake
this feature can make, so the reply state is always refreshed before the
sequence step is queued.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import OutreachCampaignDB, OutreachContactDB, OutreachMessageDB, UserEmailAccountDB
from .inbox import InboxSyncError, fetch_feedback
from . import templates as tpl

logger = logging.getLogger(__name__)

DEFAULT_FOLLOWUP_SUBJECT = "Re: {{original_subject}}"
DEFAULT_FOLLOWUP_BODY = """Hi {{contact_name}},

Just floating this back to the top of your inbox in case it got buried. Still
very interested in {{role_hint}} at {{company_name}}, and happy to work around
whatever your hiring timeline looks like.

Thanks again,
{{my_name}}"""


async def sync_feedback(user_id: int, session: AsyncSession, lookback_days: int = 30) -> dict:
    """Pull replies/bounces from the user's mailbox and record them.

    Never raises on IMAP trouble — the error is stored on the account and
    returned, so a broken mailbox degrades the feature instead of the app.
    """
    stats = {"scanned": 0, "replies": 0, "bounces": 0, "error": None}

    account = (
        await session.execute(select(UserEmailAccountDB).where(UserEmailAccountDB.user_id == user_id))
    ).scalar_one_or_none()
    if account is None:
        stats["error"] = "No sending account configured."
        return stats

    try:
        loop = asyncio.get_running_loop()
        feedback = await loop.run_in_executor(None, fetch_feedback, account, lookback_days)
    except InboxSyncError as e:
        account.last_sync_error = str(e)[:1000]
        await session.flush()
        stats["error"] = str(e)
        return stats
    except Exception as e:
        logger.exception("Unexpected inbox sync failure")
        account.last_sync_error = f"Unexpected sync failure: {e}"[:1000]
        await session.flush()
        stats["error"] = str(e)
        return stats

    stats["scanned"] = len(feedback)

    if feedback:
        messages = (
            await session.execute(
                select(OutreachMessageDB).where(
                    OutreachMessageDB.user_id == user_id,
                    OutreachMessageDB.message_id.in_(list(feedback.keys())),
                )
            )
        ).scalars().all()

        for message in messages:
            entry = feedback.get(message.message_id)
            if entry is None:
                continue

            if entry["kind"] == "bounce":
                if message.bounced_at is None:
                    message.bounced_at = entry["at"]
                    message.bounce_reason = entry["detail"]
                    stats["bounces"] += 1
            elif message.replied_at is None:
                message.replied_at = entry["at"]
                message.reply_from = entry["from"]
                message.reply_snippet = entry["detail"]
                stats["replies"] += 1

    account.last_synced_at = datetime.utcnow()
    account.last_sync_error = None
    await session.flush()
    return stats


def _thread_state(message: OutreachMessageDB) -> tuple[bool, bool]:
    """(replied, bounced) for a message — checked on the message itself only.

    Follow-ups carry their own feedback, but the decision to send one is made
    against the step-1 row, which is where a reply to the thread lands.
    """
    return message.replied_at is not None, message.bounced_at is not None


async def queue_due_followups(user_id: int, session: AsyncSession) -> dict:
    """Queue step-2 emails for sends that are old enough and got no response."""
    stats = {"queued": 0, "skipped_replied": 0, "skipped_bounced": 0}

    account = (
        await session.execute(select(UserEmailAccountDB).where(UserEmailAccountDB.user_id == user_id))
    ).scalar_one_or_none()
    if account is None:
        return stats

    campaigns = (
        await session.execute(
            select(OutreachCampaignDB).where(
                OutreachCampaignDB.user_id == user_id,
                OutreachCampaignDB.followup_enabled.is_(True),
            )
        )
    ).scalars().all()

    for campaign in campaigns:
        cutoff = datetime.utcnow() - timedelta(days=campaign.followup_after_days)

        originals = (
            await session.execute(
                select(OutreachMessageDB).where(
                    OutreachMessageDB.campaign_id == campaign.id,
                    OutreachMessageDB.step == 1,
                    OutreachMessageDB.status == "sent",
                    OutreachMessageDB.sent_at <= cutoff,
                )
            )
        ).scalars().all()
        if not originals:
            continue

        # One query for every follow-up already spawned in this campaign beats
        # one existence check per recipient.
        existing_parents = set(
            (
                await session.execute(
                    select(OutreachMessageDB.parent_id).where(
                        OutreachMessageDB.campaign_id == campaign.id,
                        OutreachMessageDB.step == 2,
                    )
                )
            ).scalars().all()
        )

        for original in originals:
            if original.id in existing_parents:
                continue

            replied, bounced = _thread_state(original)
            if replied:
                stats["skipped_replied"] += 1
                continue
            if bounced:
                stats["skipped_bounced"] += 1
                continue

            contact = (
                await session.execute(
                    select(OutreachContactDB).where(OutreachContactDB.id == original.contact_id)
                )
            ).scalar_one_or_none() if original.contact_id else None

            context = {
                "contact_name": original.to_name or "",
                "company_name": original.company_name or "your team",
                "role_hint": (contact.role_hint if contact else None) or "the role",
                "my_name": account.from_name,
                "original_subject": original.subject,
            }
            subject_template = campaign.followup_subject_template or DEFAULT_FOLLOWUP_SUBJECT
            body_template = campaign.followup_body_template or DEFAULT_FOLLOWUP_BODY

            body = tpl.render(body_template, context)
            if account.signature:
                body = f"{body.rstrip()}\n\n{account.signature.strip()}"

            session.add(OutreachMessageDB(
                user_id=user_id,
                campaign_id=campaign.id,
                contact_id=original.contact_id,
                parent_id=original.id,
                step=2,
                to_email=original.to_email,
                to_name=original.to_name,
                company_name=original.company_name,
                subject=tpl.render(subject_template, context),
                body=body,
                attached_resume=False,   # they already have it from step 1
                status="queued",
                scheduled_for=datetime.utcnow(),
            ))
            stats["queued"] += 1

        if stats["queued"] and campaign.status == "completed":
            # New work arrived for a campaign that had finished — reopen it so
            # the drain picks it up on the next run.
            campaign.status = "paused"
            campaign.completed_at = None

    await session.flush()
    return stats
