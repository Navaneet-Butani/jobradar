"""Merge-field rendering for outreach, plus optional per-contact LLM rewrite.

Templates use `{{field}}` placeholders. Unknown fields render as empty
rather than raising — a half-filled CSV row should still produce a sendable
email, and the preview shows the user exactly what the recipient gets.
"""

import logging
import re
from typing import Optional

import httpx

from ..llm.gemini import generate_text, is_enabled

logger = logging.getLogger(__name__)

FIELD_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")

MERGE_FIELDS = (
    "contact_name",
    "company_name",
    "title",
    "role_hint",
    "my_name",
    "my_experience",
    "my_skills",
)

DEFAULT_SUBJECT = "{{my_name}} — {{role_hint}} at {{company_name}}"

DEFAULT_BODY = """Hi {{contact_name}},

I'm {{my_name}}, a {{my_experience}} engineer working mainly with {{my_skills}}.

I'm reaching out about {{role_hint}} openings at {{company_name}}. My resume is
attached — happy to share more detail on anything relevant.

Thanks for your time,
{{my_name}}"""


def render(template: str, context: dict) -> str:
    """Substitute {{fields}}. Missing/empty values collapse the surrounding line gracefully."""
    def substitute(match: re.Match) -> str:
        return str(context.get(match.group(1)) or "").strip()

    text = FIELD_RE.sub(substitute, template)
    # A greeting whose name didn't resolve ("Hi ,") reads worse than no name.
    text = re.sub(r"(?im)^(hi|hello|dear)\s*,", r"\1 there,", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def template_fields(template: str) -> set[str]:
    return set(FIELD_RE.findall(template))


def unknown_fields(template: str) -> set[str]:
    return template_fields(template) - set(MERGE_FIELDS)


def build_context(
    contact_name: Optional[str],
    company_name: Optional[str],
    title: Optional[str],
    role_hint: Optional[str],
    my_name: str,
    years_exp: Optional[float],
    skills: Optional[list],
) -> dict:
    experience = f"{float(years_exp):g}-year" if years_exp else ""
    return {
        "contact_name": contact_name or "",
        "company_name": company_name or "your team",
        "title": title or "",
        "role_hint": role_hint or "engineering",
        "my_name": my_name,
        "my_experience": experience,
        "my_skills": ", ".join(str(s) for s in (skills or [])[:4]),
    }


async def personalize(body: str, company_name: Optional[str], role_hint: Optional[str]) -> Optional[str]:
    """Ask the LLM to make one rendered email specific to the company.

    Returns None on any failure — the caller keeps the merge-field version.
    Deliberately conservative: it may only adjust wording, never add claims.
    """
    if not is_enabled() or not company_name:
        return None

    prompt = (
        "Rewrite this job-enquiry email so it reads as written specifically for this company. "
        "Rules: keep it under 140 words, keep the same facts, invent nothing about the company or "
        "the candidate, add no new claims of experience, keep the sign-off exactly as it is, and "
        "return only the email body as plain text with no subject line and no commentary.\n\n"
        f"COMPANY: {company_name}\n"
        f"ROLE INTEREST: {role_hint or 'engineering roles'}\n\n"
        f"EMAIL:\n{body}\n"
    )

    async with httpx.AsyncClient() as client:
        result = await generate_text(prompt, client, max_output_tokens=400)

    return result.strip() if result else None
