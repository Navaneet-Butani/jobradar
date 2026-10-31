"""Phase 3 Task 5.1 — daily/weekly digest emails.

Standalone from the (currently-unused) email queue/worker — sends
directly through EmailService's configured transport. Meant to be run
from a scheduled script (see scripts/send_digest.py), not from a request.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import CompanyDB, JobDB, JobProfileDB, JobSourceDB, MatchDB, UserDB
from .email_service import get_email_service

logger = logging.getLogger(__name__)

DAILY_DIGEST_LIMIT = 10


async def _matches_for_profile(
    session: AsyncSession, profile_id: int, limit: int
) -> list[dict]:
    rows = (
        await session.execute(
            select(MatchDB, JobDB, CompanyDB.name, JobSourceDB.name)
            .join(JobDB, JobDB.id == MatchDB.job_id)
            .outerjoin(CompanyDB, CompanyDB.id == JobDB.company_id)
            .outerjoin(JobSourceDB, JobSourceDB.id == JobDB.source_id)
            .where(
                MatchDB.job_profile_id == profile_id,
                JobDB.status == "active",
                MatchDB.state == "new",
            )
            .order_by(MatchDB.score.desc())
            .limit(limit)
        )
    ).all()

    matches = []
    for match, job, company_name, source_name in rows:
        matches.append({
            "title": job.title,
            "company": company_name or "Company undisclosed",
            "location": _location_label(job),
            "score": round(match.score),
            "explanation": match.explanation,
            "apply_url": job.apply_url,
            "source": source_name or "",
        })
    return matches


def _location_label(job: JobDB) -> str:
    if job.city and job.is_remote:
        return f"{job.city} · Remote"
    if job.city:
        return job.city
    if job.is_remote:
        return "Remote (global)" if job.remote_scope == "global" else "Remote (India)"
    return "Location unspecified"


async def send_daily_digest(session: AsyncSession) -> dict:
    """Top N new matches per active profile, one email per user (profiles grouped)."""
    email_service = get_email_service()
    stats = {"users_emailed": 0, "profiles": 0, "matches_included": 0, "skipped_empty": 0}

    users = (await session.execute(select(UserDB).where(UserDB.is_active.is_(True)))).scalars().all()

    for user in users:
        profiles = (
            await session.execute(
                select(JobProfileDB).where(JobProfileDB.user_id == user.id, JobProfileDB.is_active.is_(True))
            )
        ).scalars().all()
        if not profiles:
            continue

        sections = []
        for profile in profiles:
            matches = await _matches_for_profile(session, profile.id, DAILY_DIGEST_LIMIT)
            if not matches:
                continue
            sections.append({"profile_name": profile.name, "matches": matches})
            stats["matches_included"] += len(matches)
            stats["profiles"] += 1

        if not sections:
            stats["skipped_empty"] += 1
            continue

        total = sum(len(s["matches"]) for s in sections)
        sent = await email_service.send_direct_email(
            to_email=user.email,
            subject=f"{total} new match{'es' if total != 1 else ''} today — JobRadar",
            template_name="match_digest",
            template_data={
                "recipient_email": user.email,
                "sections": sections,
                "total_matches": total,
                "digest_kind": "Daily",
            },
        )
        if sent:
            stats["users_emailed"] += 1
        else:
            logger.warning(f"Daily digest failed to send to {user.email}")

    return stats


async def send_weekly_summary(session: AsyncSession) -> dict:
    """Application stats + follow-ups due, per Phase 3 Task 5.1."""
    from ...repositories.application_repository import ApplicationRepository

    email_service = get_email_service()
    app_repo = ApplicationRepository()
    stats = {"users_emailed": 0}

    users = (await session.execute(select(UserDB).where(UserDB.is_active.is_(True)))).scalars().all()
    week_ago = datetime.utcnow() - timedelta(days=7)

    for user in users:
        app_stats = await app_repo.calculate_application_stats(user.id, session)
        due_applications = await app_repo.get_due_today(user.id, session)

        new_matches_result = await session.execute(
            select(func.count())
            .select_from(MatchDB)
            .join(JobProfileDB, JobProfileDB.id == MatchDB.job_profile_id)
            .where(JobProfileDB.user_id == user.id, MatchDB.surfaced_at >= week_ago)
        )
        new_matches_this_week = new_matches_result.scalar_one()

        if app_stats.total_applications == 0 and new_matches_this_week == 0:
            continue

        sent = await email_service.send_direct_email(
            to_email=user.email,
            subject="Your weekly JobRadar summary",
            template_name="weekly_summary",
            template_data={
                "recipient_email": user.email,
                "new_matches_this_week": new_matches_this_week,
                "total_applications": app_stats.total_applications,
                "applications_this_week": app_stats.applications_this_week,
                "by_status": app_stats.applications_by_status,
                "due_count": len(due_applications),
                "due_applications": due_applications[:5],
            },
        )
        if sent:
            stats["users_emailed"] += 1

    return stats
