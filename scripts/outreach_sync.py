#!/usr/bin/env python3
"""Sync outreach mailboxes, queue due follow-ups, and drain running campaigns.

Run on a schedule (see .github/workflows/outreach.yml) or by hand. Safe to
run as often as you like: every step is idempotent, and the daily send cap
is enforced inside the drain, so an extra run can't over-send.

Order is deliberate — replies are pulled BEFORE follow-ups are queued, so
nobody who already answered gets chased.

    ./venv/Scripts/python.exe -m scripts.outreach_sync
    ./venv/Scripts/python.exe -m scripts.outreach_sync --no-send   # sync only
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.core.database import db
from app.models import OutreachCampaignDB, UserEmailAccountDB
from app.services.outreach.feedback import queue_due_followups, sync_feedback
from app.services.outreach.runner import drain_campaign

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("outreach_sync")


async def run(send: bool) -> int:
    await db.connect()

    async with db.get_session() as session:
        accounts = (await session.execute(select(UserEmailAccountDB))).scalars().all()
        user_ids = [a.user_id for a in accounts]

    if not user_ids:
        logger.info("No outreach accounts configured — nothing to do.")
        return 0

    failures = 0

    for user_id in user_ids:
        async with db.get_session() as session:
            sync = await sync_feedback(user_id, session)
            if sync.get("error"):
                logger.warning(f"user {user_id}: inbox sync failed — {sync['error']}")
                failures += 1
                await session.commit()
                continue

            followups = await queue_due_followups(user_id, session)
            await session.commit()

        logger.info(
            f"user {user_id}: {sync['replies']} new replies, {sync['bounces']} bounces, "
            f"{followups['queued']} follow-ups queued "
            f"({followups['skipped_replied']} skipped — already replied, "
            f"{followups['skipped_bounced']} skipped — bounced)"
        )

    if not send:
        logger.info("--no-send given; not draining campaigns.")
        return 1 if failures else 0

    async with db.get_session() as session:
        pending = (
            await session.execute(
                select(OutreachCampaignDB.id, OutreachCampaignDB.user_id).where(
                    OutreachCampaignDB.status.in_(["running", "paused"])
                )
            )
        ).all()

    for campaign_id, user_id in pending:
        # A paused campaign holding queued follow-ups is exactly what the
        # scheduled run exists to push along.
        async with db.get_session() as session:
            campaign = (
                await session.execute(
                    select(OutreachCampaignDB).where(OutreachCampaignDB.id == campaign_id)
                )
            ).scalar_one()
            queued_exists = any(m.status == "queued" for m in campaign.messages)
            if not queued_exists:
                continue
            campaign.status = "running"
            await session.commit()

        result = await drain_campaign(campaign_id, user_id)
        logger.info(f"campaign {campaign_id}: {result}")

    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-send", action="store_true", help="sync replies/bounces only, send nothing")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(send=not args.no_send)))


if __name__ == "__main__":
    main()
