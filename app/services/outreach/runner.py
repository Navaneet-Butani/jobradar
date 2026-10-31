"""Campaign drain loop.

Runs as a FastAPI background task on its own DB session. There is no
always-on worker and no queue service — all state lives in
`outreach_messages`, so a drain that dies mid-run (API restart, laptop
sleep) leaves the campaign exactly where it stopped and the next `start`
picks up the remaining `queued` rows.

Stops on: empty queue, daily cap reached, or the campaign being paused
from the UI mid-run.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import db
from ...models import OutreachCampaignDB, OutreachMessageDB, UserEmailAccountDB, UserResumeDB
from .quota import remaining_today
from .sender import OutreachSendError, send_as_user

logger = logging.getLogger(__name__)


async def _load_attachment(user_id: int, session: AsyncSession) -> Optional[tuple[str, bytes]]:
    resume = (
        await session.execute(select(UserResumeDB).where(UserResumeDB.user_id == user_id))
    ).scalar_one_or_none()
    if resume is None or not resume.file_data:
        return None
    return resume.filename, resume.file_data


async def drain_campaign(campaign_id: int, user_id: int) -> dict:
    """Send this campaign's queued messages, paced, until the cap or the queue runs out."""
    stats = {"sent": 0, "failed": 0, "stopped_reason": "completed"}

    async with db.get_session() as session:
        campaign = (
            await session.execute(
                select(OutreachCampaignDB).where(
                    OutreachCampaignDB.id == campaign_id, OutreachCampaignDB.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if campaign is None:
            return {**stats, "stopped_reason": "campaign_missing"}

        account = (
            await session.execute(
                select(UserEmailAccountDB).where(UserEmailAccountDB.user_id == user_id)
            )
        ).scalar_one_or_none()
        if account is None:
            campaign.status = "paused"
            await session.commit()
            return {**stats, "stopped_reason": "no_email_account"}

        attachment = await _load_attachment(user_id, session) if campaign.attach_resume else None
        if campaign.attach_resume and attachment is None:
            logger.warning(
                f"Campaign {campaign_id} wants a resume attachment but no file is stored — sending without."
            )

    while True:
        async with db.get_session() as session:
            campaign = (
                await session.execute(
                    select(OutreachCampaignDB).where(OutreachCampaignDB.id == campaign_id)
                )
            ).scalar_one_or_none()
            if campaign is None or campaign.status != "running":
                stats["stopped_reason"] = "paused"
                break

            account = (
                await session.execute(
                    select(UserEmailAccountDB).where(UserEmailAccountDB.user_id == user_id)
                )
            ).scalar_one()

            if await remaining_today(user_id, account.daily_send_cap, session) <= 0:
                campaign.status = "paused"
                await session.commit()
                stats["stopped_reason"] = "daily_cap_reached"
                break

            message = (
                await session.execute(
                    select(OutreachMessageDB)
                    .where(
                        OutreachMessageDB.campaign_id == campaign_id,
                        OutreachMessageDB.status == "queued",
                    )
                    .order_by(OutreachMessageDB.id)
                    .limit(1)
                )
            ).scalar_one_or_none()

            if message is None:
                campaign.status = "completed"
                campaign.completed_at = datetime.utcnow()
                await session.commit()
                stats["stopped_reason"] = "completed"
                break

            # A follow-up threads under whatever step 1 actually got sent as.
            in_reply_to = None
            if message.parent_id:
                in_reply_to = (
                    await session.execute(
                        select(OutreachMessageDB.message_id).where(OutreachMessageDB.id == message.parent_id)
                    )
                ).scalar_one_or_none()

            try:
                sent_message_id = await send_as_user(
                    account=account,
                    to_email=message.to_email,
                    to_name=message.to_name,
                    subject=message.subject,
                    body=message.body,
                    attachment=attachment if message.attached_resume else None,
                    in_reply_to=in_reply_to,
                )
                message.status = "sent"
                message.sent_at = datetime.utcnow()
                message.message_id = sent_message_id
                message.error = None
                stats["sent"] += 1
            except OutreachSendError as e:
                message.status = "failed"
                message.error = str(e)[:1000]
                stats["failed"] += 1
                logger.warning(f"Campaign {campaign_id}: send to {message.to_email} failed — {e}")

            await session.commit()
            interval = account.send_interval_seconds

        # Pacing happens outside the session so a slow batch doesn't pin a
        # connection from the small free-tier pool for minutes at a time.
        await asyncio.sleep(max(1, interval))

    logger.info(f"Campaign {campaign_id} drain finished: {stats}")
    return stats
