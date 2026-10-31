"""Daily send accounting.

The cap is per user per day, counted in APP_TIMEZONE (default Asia/Kolkata):
a UTC day boundary would roll the counter over at 05:30 IST, which is the
wrong answer when you send a batch late at night.
"""

import logging
from datetime import datetime, timedelta

import pytz
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config.settings import settings
from ...models import OutreachMessageDB

logger = logging.getLogger(__name__)

IST = pytz.timezone(settings.app_timezone)  # name kept for callers; it is the app timezone


def ist_day_start_utc() -> datetime:
    """Start of the current IST day, as a naive UTC datetime (what we store)."""
    now_ist = datetime.now(IST)
    midnight_ist = IST.localize(datetime(now_ist.year, now_ist.month, now_ist.day))
    return midnight_ist.astimezone(pytz.UTC).replace(tzinfo=None)


async def sent_today(user_id: int, session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(OutreachMessageDB)
        .where(
            OutreachMessageDB.user_id == user_id,
            OutreachMessageDB.status == "sent",
            OutreachMessageDB.sent_at >= ist_day_start_utc(),
        )
    )
    return result.scalar_one()


async def remaining_today(user_id: int, daily_cap: int, session: AsyncSession) -> int:
    return max(0, daily_cap - await sent_today(user_id, session))


async def previously_emailed(user_id: int, emails: list[str], session: AsyncSession) -> dict[str, datetime]:
    """Map of address -> most recent send time, for addresses already contacted.

    Purely informational: the user chose not to enforce a lifetime per-contact
    cap, so this flags repeats in the preview instead of blocking them.
    """
    if not emails:
        return {}

    result = await session.execute(
        select(OutreachMessageDB.to_email, func.max(OutreachMessageDB.sent_at))
        .where(
            OutreachMessageDB.user_id == user_id,
            OutreachMessageDB.status == "sent",
            OutreachMessageDB.to_email.in_([e.lower() for e in emails]),
        )
        .group_by(OutreachMessageDB.to_email)
    )
    return {email: sent_at for email, sent_at in result.all() if sent_at}


def next_window_hint(remaining: int, queued: int) -> str:
    if remaining >= queued:
        return "All queued emails fit inside today's cap."
    days = -(-(queued - remaining) // max(1, remaining)) if remaining else None
    if days is None:
        return "Today's cap is already used up — sending resumes tomorrow."
    return f"{remaining} will go today; the rest continues over roughly {days} more day(s)."


__all__ = [
    "sent_today",
    "remaining_today",
    "previously_emailed",
    "next_window_hint",
    "ist_day_start_utc",
    "timedelta",
]
