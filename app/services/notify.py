"""Push new strong matches to a profile's chat webhook (Telegram, Discord, Slack, ntfy).

Runs at the end of every ingest (scripts/run_ingest.py) and by hand with
`python -m scripts.notify_matches`. Each match is sent once (matches.notified_at).

Webhook URL formats, set per profile on the Profile page:
  Telegram  https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>
  Discord   https://discord.com/api/webhooks/<id>/<token>
  Slack     https://hooks.slack.com/services/...
  ntfy      https://ntfy.sh/<your-topic>

Only these hosts are accepted. The server makes the request, so an arbitrary
URL would let any user make it call internal addresses.
"""

import logging
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config.settings import settings
from ..models import CompanyDB, JobDB, JobProfileDB, MatchDB

logger = logging.getLogger(__name__)

ALLOWED_HOSTS = {
    "api.telegram.org": "telegram",
    "discord.com": "discord",
    "discordapp.com": "discord",
    "hooks.slack.com": "slack",
    "ntfy.sh": "ntfy",
}
MAX_PER_MESSAGE = 10
DISCORD_LIMIT = 2000


def webhook_kind(url: Optional[str]) -> Optional[str]:
    """The platform for an allowed https webhook URL, else None."""
    if not url:
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        return None
    return ALLOWED_HOSTS.get((parsed.hostname or "").lower())


def format_message(profile_name: str, matches: List[dict]) -> str:
    lines = [f"JobRadar: {len(matches)} new match{'es' if len(matches) != 1 else ''} for {profile_name}"]
    for m in matches:
        lines.append(f"\n{m['score']} · {m['title']} at {m['company']} ({m['location']})")
        if m.get("explanation"):
            lines.append(f"  {m['explanation']}")
        lines.append(f"  {m['url']}")
    return "\n".join(lines)


def _payload(kind: str, text: str):
    if kind == "telegram":
        return {"json": {"text": text, "disable_web_page_preview": True}}
    if kind == "discord":
        return {"json": {"content": text[:DISCORD_LIMIT]}}
    if kind == "slack":
        return {"json": {"text": text}}
    return {"content": text.encode("utf-8"), "headers": {"Title": "JobRadar"}}  # ntfy: plain body


async def send(url: str, text: str, client: httpx.AsyncClient) -> bool:
    kind = webhook_kind(url)
    if not kind:
        logger.warning("Skipping notification: webhook host not allowed")
        return False
    try:
        response = await client.post(url.strip(), timeout=15.0, **_payload(kind, text))
        response.raise_for_status()
        return True
    except Exception as e:
        # Never log the URL: Telegram and Discord URLs contain the secret token.
        logger.warning(f"{kind} notification failed: {type(e).__name__}")
        return False


def _location(job: JobDB) -> str:
    if job.city:
        return f"{job.city}{' · Remote' if job.is_remote else ''}"
    return "Remote" if job.is_remote else "Location n/a"


async def notify_new_matches(session: AsyncSession, client: Optional[httpx.AsyncClient] = None) -> dict:
    """Send each profile's unsent new matches at or above NOTIFY_MIN_SCORE."""
    stats = {"profiles": 0, "sent": 0, "failed": 0}
    profiles = (await session.execute(
        select(JobProfileDB).where(JobProfileDB.is_active.is_(True), JobProfileDB.notify_webhook_url.isnot(None))
    )).scalars().all()
    own_client = client is None
    client = client or httpx.AsyncClient()
    try:
        for profile in profiles:
            if not webhook_kind(profile.notify_webhook_url):
                continue
            rows = (await session.execute(
                select(MatchDB, JobDB, CompanyDB.name)
                .join(JobDB, JobDB.id == MatchDB.job_id)
                .outerjoin(CompanyDB, CompanyDB.id == JobDB.company_id)
                .where(MatchDB.job_profile_id == profile.id, MatchDB.state == "new",
                       MatchDB.notified_at.is_(None), MatchDB.score >= settings.notify_min_score,
                       JobDB.status == "active")
                .order_by(MatchDB.score.desc())
                .limit(MAX_PER_MESSAGE)
            )).all()
            if not rows:
                continue
            stats["profiles"] += 1
            matches = [{
                "score": round(match.score), "title": job.title, "company": company or "Company n/a",
                "location": _location(job), "explanation": match.explanation,
                "url": f"{settings.frontend_url.rstrip('/')}/jobs/{job.id}?profileId={profile.id}",
            } for match, job, company in rows]
            if await send(profile.notify_webhook_url, format_message(profile.name, matches), client):
                await session.execute(
                    update(MatchDB)
                    .where(MatchDB.job_profile_id == profile.id, MatchDB.job_id.in_([j.id for _, j, _ in rows]))
                    .values(notified_at=datetime.utcnow())
                )
                await session.commit()
                stats["sent"] += len(rows)
            else:
                stats["failed"] += 1
    finally:
        if own_client:
            await client.aclose()
    return stats
