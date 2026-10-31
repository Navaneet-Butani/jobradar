"""Phase 3 Task 2.2 — LLM follow-up draft generation.

Given an application's job, company, applied date, and status timeline,
produce a short, specific follow-up message. The user reviews and sends
it themselves — this never sends anything on its own.
"""

import logging
from datetime import datetime

import httpx

from .llm.gemini import generate_text, is_enabled

logger = logging.getLogger(__name__)


def _build_prompt(job_title: str, company_name: str, applied_date: datetime, timeline: list[dict]) -> str:
    days_since = max(0, (datetime.utcnow() - applied_date).days)

    history = "No status changes since applying."
    if timeline:
        lines = [
            f"- {entry.get('from_status')} -> {entry.get('to_status')} ({entry.get('at', '')[:10]})"
            for entry in timeline
        ]
        history = "\n".join(lines)

    return (
        "Write a short follow-up message from a candidate to a hiring team, checking in on "
        "their application. Be specific and professional, not generic or templated — reference "
        "the actual role and how long it's been. 3-5 sentences. No subject line, no sign-off "
        "name (you don't know the candidate's name — end with 'Best regards,' and nothing after "
        "it, the candidate will add their own name), no placeholder brackets. Just the message "
        "body ready to send.\n\n"
        f"Role: {job_title}\n"
        f"Company: {company_name}\n"
        f"Applied: {days_since} days ago\n"
        f"Status history:\n{history}\n"
    )


async def generate_followup_draft(
    job_title: str, company_name: str, applied_date: datetime, timeline: list[dict]
) -> str | None:
    """Returns the draft text, or None if the LLM is disabled or the call fails."""
    if not is_enabled():
        return None

    prompt = _build_prompt(job_title, company_name, applied_date, timeline)
    async with httpx.AsyncClient() as client:
        draft = await generate_text(prompt, client, max_output_tokens=250)
    return draft.strip() if draft else None
