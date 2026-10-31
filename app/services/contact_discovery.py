"""Phase 3 Task 3.1 — contact discovery for an application packet.

Resolution order, straight from `04-PHASE-3-TRACKING.md` §3.1:

  1. ATS form (Greenhouse/Lever/Ashby) — preferred, it *is* the hiring team.
  2. Emails already harvested from the JD into `job_details.contact_emails`.
  3. The company careers page — fetch once, regex for role-based addresses.

We never scrape people. Only role-based addresses (careers@, hr@, jobs@,
talent@ and friends) are accepted; a personal-looking address found on a
careers page is discarded.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CompanyDB, JobDB, JobDetailDB

logger = logging.getLogger(__name__)

ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com")
ATS_LABELS = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "workday": "Workday",
}

# Role-based local parts only — never a person's name.
ROLE_LOCAL_PARTS = (
    "careers", "career", "jobs", "job", "hr", "hiring", "recruit", "recruiting",
    "recruitment", "talent", "people", "work", "join", "apply", "resume", "cv",
)
GENERIC_LOCAL_PARTS = ("info", "contact", "hello", "enquiry", "enquiries", "inquiry", "reach")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Addresses that look role-based but belong to the site's vendors, not the employer.
BLOCKED_DOMAINS = ("example.com", "sentry.io", "wixpress.com", "godaddy.com", "squarespace.com")

CAREERS_PATHS = ("/careers", "/careers/", "/jobs", "/about/careers", "/company/careers")

# `companies.website` is empty across the board (the ingest pipeline never fills
# it), so the only company-owned URL we reliably hold is a job's apply_url — and
# only when it isn't pointing back at the board we scraped it from.
AGGREGATOR_HOSTS = (
    "hirist.tech", "instahyre.com", "indeed.com", "linkedin.com", "naukri.com",
    "glassdoor.com", "monsterindia.com", "shine.com", "timesjobs.com",
    "remoteok.com", "arbeitnow.com", "remotive.com", "himalayas.app",
)
RECHECK_AFTER = timedelta(days=30)
FETCH_TIMEOUT = 8.0
USER_AGENT = "JobRadar/1.0 (personal job search; contact discovery)"


def email_tier(email: str) -> Optional[int]:
    """0 = a hiring address, 1 = a generic company inbox, None = not usable.

    Indian company sites very often publish only `info@` — a weak lead, but a
    real one, so it's kept and labelled as generic rather than thrown away.
    """
    local, _, domain = email.lower().partition("@")
    if any(domain.endswith(blocked) for blocked in BLOCKED_DOMAINS):
        return None
    if any(local == part or local.startswith(part) for part in ROLE_LOCAL_PARTS):
        return 0
    if local in GENERIC_LOCAL_PARTS:
        return 1
    return None


def is_role_email(email: str) -> bool:
    """True only for hiring addresses — never a personal one."""
    return email_tier(email) == 0


def detect_ats(apply_url: Optional[str], ats_type: Optional[str]) -> Optional[str]:
    """Return a human label for the ATS behind this posting, or None."""
    if ats_type and ats_type.lower() in ATS_LABELS:
        return ATS_LABELS[ats_type.lower()]
    host = urlparse(apply_url or "").netloc.lower()
    for ats_host in ATS_HOSTS:
        if host.endswith(ats_host) or f".{ats_host}" in host:
            return ATS_LABELS.get(ats_host.split(".")[0], ats_host)
    return None


def _is_company_owned(url: Optional[str]) -> bool:
    host = urlparse(url or "").netloc.lower()
    if not host:
        return False
    return not any(host.endswith(h) for h in AGGREGATOR_HOSTS + ATS_HOSTS)


def _candidate_pages(company: CompanyDB, apply_url: Optional[str] = None) -> list[str]:
    pages: list[str] = []
    if company.career_page_url:
        pages.append(company.career_page_url)
    if company.website:
        root = company.website if company.website.startswith("http") else f"https://{company.website}"
        pages.append(root)
        pages.extend(urljoin(root, path) for path in CAREERS_PATHS[:2])
    if _is_company_owned(apply_url):
        parsed = urlparse(apply_url)
        pages.append(apply_url)
        pages.append(urljoin(f"{parsed.scheme}://{parsed.netloc}", "/careers"))
    # Three fetches is the politeness ceiling — these are other people's servers.
    return list(dict.fromkeys(pages))[:3]


async def _scrape_careers_email(company: CompanyDB, apply_url: Optional[str] = None) -> Optional[str]:
    pages = _candidate_pages(company, apply_url)
    if not pages:
        return None

    best: Optional[tuple[int, str]] = None

    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        for url in pages:
            try:
                response = await client.get(url)
                # Even a 404 page usually carries the site-wide footer address.
                if response.status_code >= 500 or not response.text:
                    continue
                page_domain = urlparse(str(response.url)).netloc.lower().removeprefix("www.")
                for email in EMAIL_RE.findall(response.text[:400_000]):
                    email = email.lower()
                    # Only the employer's own domain — not their vendors' or partners'.
                    if not email.endswith(page_domain):
                        continue
                    tier = email_tier(email)
                    if tier is None:
                        continue
                    if best is None or tier < best[0]:
                        best = (tier, email)
                    if tier == 0:
                        return email
            except Exception as e:
                logger.debug(f"Careers-page fetch failed for {url}: {e}")

    return best[1] if best else None


async def _company_careers_email(
    company: Optional[CompanyDB], apply_url: Optional[str], session: AsyncSession
) -> Optional[str]:
    """Cached per company — a miss is recorded too, so it isn't refetched every packet."""
    if company is None:
        return None

    fresh = company.contact_checked_at and (datetime.utcnow() - company.contact_checked_at) < RECHECK_AFTER
    if fresh:
        return company.contact_email

    email = await _scrape_careers_email(company, apply_url)
    company.contact_email = email
    company.contact_checked_at = datetime.utcnow()
    await session.flush()
    return email


async def discover_contact(
    job: JobDB,
    detail: Optional[JobDetailDB],
    company: Optional[CompanyDB],
    session: AsyncSession,
) -> dict:
    """Best available contact for a job. Always returns a dict; `method` is None when nothing was found."""
    ats = detect_ats(job.apply_url, company.ats_type if company else None)
    if ats:
        return {
            "method": "ats_form",
            "label": f"{ats} application form",
            "email": None,
            "url": job.apply_url,
            "note": f"This posting is on {ats} — the form goes straight to the hiring team. Apply there first.",
        }

    if job.apply_email:
        return {
            "method": "apply_email",
            "label": "Application address given by the posting",
            "email": job.apply_email,
            "url": job.apply_url,
            "note": "The posting names this address as the way to apply — send the application here.",
        }

    jd_emails = [e for e in (detail.contact_emails or []) if e] if detail else []
    if jd_emails:
        return {
            "method": "jd_email",
            "label": "Email listed in the job description",
            "email": jd_emails[0],
            "url": job.apply_url,
            "note": "Taken from the job description itself.",
        }

    careers_email = await _company_careers_email(company, job.apply_url, session)
    if careers_email:
        hiring = is_role_email(careers_email)
        return {
            "method": "careers_page",
            "label": "Careers-page address" if hiring else "General company inbox",
            "email": careers_email,
            "url": (company.career_page_url or company.website or job.apply_url) if company else job.apply_url,
            "note": (
                "Hiring address found on the company site. Apply through the posting first — outreach is a follow-up, never a bypass."
                if hiring
                else "Only a general inbox was published — no hiring address. Weak lead: apply through the posting first, and expect this to go to reception."
            ),
        }

    return {
        "method": None,
        "label": "No contact found",
        "email": None,
        "url": job.apply_url,
        "note": "Apply through the posting link. Searching LinkedIn for the role's recruiter by hand is the next-best step.",
    }
