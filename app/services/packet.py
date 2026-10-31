"""Phase 3 Task 3 — application packet generator.

The approved alternative to auto-applying. Given a job and a job profile,
assemble everything needed to send one good application by hand in ~3
minutes: the direct apply link, resume bullets rewritten in the JD's
language, a cover note, whatever contact is discoverable, and the standard
answers every Indian application form asks for.

Nothing here submits anything. Nothing here emails anyone.
"""

import logging
from typing import Optional

import html2text
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CompanyDB, JobDB, JobDetailDB, JobProfileDB, UserResumeDB
from .contact_discovery import detect_ats, discover_contact
from .llm.gemini import generate_json, is_enabled

logger = logging.getLogger(__name__)

MAX_JD_CHARS = 6000       # enough for the JD's actual language, small enough for the free tier
MAX_RESUME_CHARS = 8000
LLM_MAX_OUTPUT_TOKENS = 1200

_html = html2text.HTML2Text()
_html.ignore_links = True
_html.ignore_images = True
_html.body_width = 0


def _to_text(value: Optional[str]) -> str:
    if not value:
        return ""
    if "<" in value and ">" in value:
        return _html.handle(value).strip()
    return value.strip()


def _job_description(job: JobDB, detail: Optional[JobDetailDB]) -> str:
    parts = [job.title]
    if job.skills_required:
        parts.append("Skills listed: " + ", ".join(str(s) for s in job.skills_required))
    if detail:
        for section in (detail.description, detail.requirements, detail.responsibilities):
            text = _to_text(section)
            if text:
                parts.append(text)
    return "\n\n".join(p for p in parts if p)[:MAX_JD_CHARS]


def _build_prompt(job_title: str, company_name: str, jd_text: str, resume_text: str) -> str:
    return (
        "You are helping a candidate apply to one specific job. Using their resume and the "
        "job description below, produce JSON with exactly two keys:\n\n"
        '  "bullets": an array of 4 or 5 resume bullet points, rewritten from things the '
        "candidate has ACTUALLY done, using the vocabulary the job description uses. Keep every "
        "number and technology that is already in the resume. Invent nothing — no new employers, "
        "no new metrics, no skills the resume doesn't show. One sentence each, starting with a "
        "strong verb.\n"
        '  "cover_note": a 4-6 sentence note to the hiring team. Specific to this role and this '
        "company — reference something concrete from the job description. No greeting line, no "
        "sign-off name, no placeholder brackets. Plain text.\n\n"
        "Return only the JSON object.\n\n"
        f"ROLE: {job_title}\n"
        f"COMPANY: {company_name}\n\n"
        f"JOB DESCRIPTION:\n{jd_text}\n\n"
        f"CANDIDATE RESUME:\n{resume_text}\n"
    )


def _format_ctc(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    lakhs = float(value) / 100000
    return f"₹{lakhs:.1f} LPA"


def _standard_answers(profile: JobProfileDB) -> dict:
    notice = profile.notice_period_days
    return {
        "notice_period": f"{notice} days" if notice is not None else None,
        "current_ctc": _format_ctc(profile.current_ctc_inr),
        "expected_ctc": _format_ctc(profile.expected_ctc_inr),
        "willing_to_relocate": "Yes" if profile.willing_to_relocate else "No",
        "total_experience": f"{float(profile.years_exp):g} years",
    }


async def _generate_llm_sections(
    job_title: str, company_name: str, jd_text: str, resume_text: str
) -> tuple[list[str], Optional[str]]:
    prompt = _build_prompt(job_title, company_name, jd_text, resume_text[:MAX_RESUME_CHARS])
    async with httpx.AsyncClient() as client:
        result = await generate_json(prompt, client, max_output_tokens=LLM_MAX_OUTPUT_TOKENS)

    if not isinstance(result, dict):
        return [], None

    bullets = [str(b).strip() for b in (result.get("bullets") or []) if str(b).strip()]
    cover_note = result.get("cover_note")
    cover_note = str(cover_note).strip() if cover_note else None
    return bullets[:5], cover_note


async def build_packet(
    user_id: int, job_id: int, profile: JobProfileDB, session: AsyncSession
) -> Optional[dict]:
    """Assemble the packet. Returns None if the job doesn't exist.

    Every optional piece degrades on its own: a missing resume drops the
    bullets, an LLM failure drops bullets and cover note, an undiscoverable
    contact leaves the apply link. The packet is always usable.
    """
    row = (
        await session.execute(
            select(JobDB, JobDetailDB, CompanyDB)
            .outerjoin(JobDetailDB, JobDetailDB.job_id == JobDB.id)
            .outerjoin(CompanyDB, CompanyDB.id == JobDB.company_id)
            .where(JobDB.id == job_id)
        )
    ).first()
    if row is None:
        return None

    job, detail, company = row
    company_name = company.name if company else "the company"
    warnings: list[str] = []

    resume = (
        await session.execute(select(UserResumeDB).where(UserResumeDB.user_id == user_id))
    ).scalar_one_or_none()

    bullets: list[str] = []
    cover_note: Optional[str] = None

    if resume is None:
        warnings.append("No resume on file — upload one on the Profile page to get tailored bullets.")
    elif not is_enabled():
        warnings.append("LLM is not configured, so bullets and the cover note were skipped.")
    else:
        jd_text = _job_description(job, detail)
        bullets, cover_note = await _generate_llm_sections(
            job.title, company_name, jd_text, resume.content_text
        )
        if not bullets and not cover_note:
            warnings.append("The LLM call didn't come back — try generating again in a moment.")

    contact = await discover_contact(job, detail, company, session)

    answers = _standard_answers(profile)
    if answers["notice_period"] is None or answers["expected_ctc"] is None:
        warnings.append("Notice period / CTC aren't set on this profile — fill them in on the Profile page.")

    ats_label = detect_ats(job.apply_url, company.ats_type if company else None)

    return {
        "job_id": job.id,
        "title": job.title,
        "company_name": company.name if company else None,
        "apply": {
            "url": job.apply_url,
            "is_direct_ats": ats_label is not None,
            "ats_label": ats_label,
            "note": (
                f"Direct {ats_label} link — this goes straight to the hiring team."
                if ats_label
                else "Aggregator link — check the company's own careers page for a direct posting before applying."
            ),
        },
        "bullets": bullets,
        "cover_note": cover_note,
        "contact": contact,
        "answers": answers,
        "resume_filename": resume.filename if resume else None,
        "warnings": warnings,
    }
