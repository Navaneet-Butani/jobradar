"""Promote fields out of `job_details.raw_data` into real columns.

Ground rule 5 says always store the raw source payload, and we do — which
turned out to mean we were sitting on a lot of data nobody could see. Every
`companies` row had a NULL website, logo, industry and headquarters while
Hirist was shipping an AmbitionBox company profile with each job and
Instahyre an employer blurb with a logo. Same story for the recruiter who
posted a Hirist job, the board's applicant/view counters, and the contact
addresses JobSpy scrapes off Indeed.

This module holds one extractor per source. It reads raw payloads that are
already in the database — no network calls — and fills columns that are
currently NULL, so it is safe to re-run and safe to run after a source
changes its shape. The single exception is JOB_AUTHORITATIVE_FIELDS, where a
figure the source states outright replaces one this codebase inferred.

Called two ways:
  * `scripts/enrich_from_raw.py` for a full backfill.
  * `scripts/run_ingest.py` after ingest, scoped to the new rows via `since`.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Hosts that are job boards, not employers. A "company URL" pointing at one of
# these is the board's own profile page and must not be stored as a website.
AGGREGATOR_HOSTS = (
    "indeed.com", "linkedin.com", "glassdoor.com", "naukri.com", "hirist.tech",
    "instahyre.com", "monster.com", "shine.com", "timesjobs.com", "himalayas.app",
    "remotive.com", "arbeitnow.com", "ziprecruiter.com", "simplyhired.com",
)

# Columns this module may write, per table. Anything not listed is off limits.
JOB_FIELDS = (
    "poster_name", "poster_title", "source_applicant_count", "source_view_count",
    "apply_email", "min_exp_years", "max_exp_years",
)

# The one exception to "never overwrite". These columns are normally filled by
# ExperienceParser guessing off the description, or off a seniority word in the
# title when there is no description — which is how 3,972 Hirist jobs ended up
# claiming "5+ yrs" while the board itself said 10-15. A figure the source
# states outright replaces a guess; everything else in JOB_FIELDS still only
# fills NULLs.
JOB_AUTHORITATIVE_FIELDS = ("min_exp_years", "max_exp_years")
COMPANY_FIELDS = (
    "website", "logo_url", "description", "headquarters", "industry", "founded_year",
    "employee_count", "employee_range", "tagline", "rating", "rating_count",
    "rating_url", "rating_source",
)

MAX_DESCRIPTION_CHARS = 4000


@dataclass
class Enrichment:
    """Column values derived from one raw payload."""

    job: Dict[str, Any] = field(default_factory=dict)
    company: Dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# value coercion
# --------------------------------------------------------------------------

def _clean_str(value: Any, limit: int = 255) -> Optional[str]:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value or text_value.lower() in ("none", "null", "n/a", "-"):
        return None
    return text_value[:limit]


def _clean_int(value: Any, *, minimum: int = 0, maximum: Optional[int] = None) -> Optional[int]:
    try:
        number = int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None
    if number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def _clean_float(value: Any, *, minimum: float, maximum: float) -> Optional[float]:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if number < minimum or number > maximum:
        return None
    return round(number, 2)


def _clean_url(value: Any, *, allow_aggregators: bool = False) -> Optional[str]:
    url = _clean_str(value, limit=500)
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    host = (urlparse(url).hostname or "").lower()
    if not host or "." not in host:
        return None
    if not allow_aggregators and any(host == a or host.endswith(f".{a}") for a in AGGREGATOR_HOSTS):
        return None
    return url


def _clean_email(value: Any) -> Optional[str]:
    """JobSpy hands back either a single address or a list of them."""
    if isinstance(value, (list, tuple)):
        value = next((v for v in value if v), None)
    email = _clean_str(value)
    if not email or "@" not in email:
        return None
    email = email.split(",")[0].strip()
    return email if "@" in email and "." in email.split("@")[-1] else None


def _clean_year(value: Any) -> Optional[int]:
    year = _clean_int(value, minimum=1800, maximum=datetime.now().year)
    return year


def _dig(payload: Dict[str, Any], *path: str) -> Any:
    """Walk a nested dict, returning None the moment the path breaks."""
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


# --------------------------------------------------------------------------
# per-source extractors
# --------------------------------------------------------------------------

def _hirist(raw: Dict[str, Any]) -> Enrichment:
    """Hirist ships the richest payload of any source we have.

    `creatorDomainName` is the posting recruiter's email domain. For a direct
    employer post that is the company's own domain; for a consultancy post it
    is the consultancy's. It is still the best company URL available for these
    rows, and the company page labels where the link came from.
    """
    out = Enrichment()

    out.job["poster_name"] = _clean_str(_dig(raw, "recruiter", "recruiterName"))
    out.job["poster_title"] = _clean_str(_dig(raw, "recruiter", "designation"))
    out.job["source_applicant_count"] = _clean_int(raw.get("applyCount"))
    out.job["source_view_count"] = _clean_int(raw.get("hits"))

    # `min`/`max` are years of experience, not salary (that is minSal/maxSal).
    min_exp = _clean_int(raw.get("min"), maximum=50)
    max_exp = _clean_int(raw.get("max"), maximum=50)
    if min_exp is not None and max_exp is not None and min_exp > max_exp:
        min_exp, max_exp = max_exp, min_exp
    out.job["min_exp_years"] = min_exp
    out.job["max_exp_years"] = max_exp

    company = raw.get("companyData") or {}
    ambition = company.get("ambitionBoxInfo") or {}

    out.company["website"] = _clean_url(raw.get("creatorDomainName"))
    out.company["logo_url"] = _clean_url(
        company.get("logoPath") or company.get("logo") or company.get("companyLogoFilePath"),
        allow_aggregators=True,
    )
    out.company["headquarters"] = _clean_str(ambition.get("hq"))
    out.company["industry"] = _clean_str(ambition.get("primaryIndustry"), limit=100)
    out.company["founded_year"] = _clean_year(ambition.get("foundedYear"))
    out.company["employee_range"] = _clean_str(ambition.get("totalEmployeesIndia"), limit=50)
    out.company["description"] = _clean_str(ambition.get("aboutCompany"), limit=MAX_DESCRIPTION_CHARS)

    rating = _clean_float(ambition.get("aggregateRating"), minimum=0, maximum=5)
    if rating:
        out.company["rating"] = rating
        out.company["rating_count"] = _clean_int(ambition.get("reviewsCount"))
        out.company["rating_url"] = _clean_url(ambition.get("url"), allow_aggregators=True)
        out.company["rating_source"] = "ambitionbox"

    return out


def _instahyre(raw: Dict[str, Any]) -> Enrichment:
    """No recruiter and no job description in the feed — employer profile only."""
    out = Enrichment()
    employer = raw.get("employer") or {}

    out.company["logo_url"] = _clean_url(employer.get("profile_image_src"), allow_aggregators=True)
    out.company["description"] = _clean_str(employer.get("instahyre_note"), limit=MAX_DESCRIPTION_CHARS)
    out.company["tagline"] = _clean_str(employer.get("company_tagline"))
    out.company["founded_year"] = _clean_year(employer.get("company_founded"))
    out.company["employee_count"] = _clean_int(employer.get("employee_count"), minimum=1)

    return out


def _jobspy(raw: Dict[str, Any]) -> Enrichment:
    """LinkedIn/Indeed via python-jobspy.

    `company_url` is the board's employer profile (indeed.com/cmp/...), so it
    is only accepted when it survives the aggregator filter; `company_url_direct`
    is the employer's own site and is preferred.
    """
    out = Enrichment()

    out.job["apply_email"] = _clean_email(raw.get("emails"))

    out.company["website"] = _clean_url(raw.get("company_url_direct")) or _clean_url(raw.get("company_url"))
    out.company["logo_url"] = _clean_url(raw.get("company_logo"), allow_aggregators=True)
    out.company["industry"] = _clean_str(raw.get("company_industry"), limit=100)
    out.company["description"] = _clean_str(raw.get("company_description"), limit=MAX_DESCRIPTION_CHARS)
    out.company["employee_range"] = _clean_str(raw.get("company_num_employees"), limit=50)

    rating = _clean_float(raw.get("company_rating"), minimum=0, maximum=5)
    if rating:
        out.company["rating"] = rating
        out.company["rating_count"] = _clean_int(raw.get("company_reviews_count"))
        out.company["rating_url"] = _clean_url(raw.get("company_url"), allow_aggregators=True)
        out.company["rating_source"] = _clean_str(raw.get("site"), limit=50) or "jobspy"

    return out


def _linkedin(raw: Dict[str, Any]) -> Enrichment:
    """Guest search cards carry a company logo off LinkedIn's CDN.

    `company_url` is deliberately not used: it always points at
    linkedin.com/company/..., which is the board's own profile page, not the
    employer's site — exactly what AGGREGATOR_HOSTS exists to reject.
    """
    out = Enrichment()
    out.company["logo_url"] = _clean_url(raw.get("company_logo"), allow_aggregators=True)
    return out


def _himalayas(raw: Dict[str, Any]) -> Enrichment:
    out = Enrichment()
    out.company["logo_url"] = _clean_url(raw.get("companyLogo"), allow_aggregators=True)
    return out


def _remotive(raw: Dict[str, Any]) -> Enrichment:
    out = Enrichment()
    out.company["logo_url"] = _clean_url(
        raw.get("company_logo_url") or raw.get("company_logo"), allow_aggregators=True
    )
    return out


EXTRACTORS = {
    "hirist": _hirist,
    "instahyre": _instahyre,
    "jobspy": _jobspy,
    "linkedin": _linkedin,
    "himalayas": _himalayas,
    "remotive": _remotive,
}

SUPPORTED_SOURCES = tuple(EXTRACTORS)


def extract_enrichment(source_name: str, raw: Optional[Dict[str, Any]]) -> Enrichment:
    """Derive column values from one raw payload. Never raises."""
    extractor = EXTRACTORS.get((source_name or "").lower())
    if not extractor or not isinstance(raw, dict):
        return Enrichment()
    try:
        result = extractor(raw)
    except Exception as e:  # a source changing shape must not break ingest
        logger.warning(f"Enrichment extractor failed for {source_name}: {e}")
        return Enrichment()

    return Enrichment(
        job={k: v for k, v in result.job.items() if v is not None and k in JOB_FIELDS},
        company={k: v for k, v in result.company.items() if v is not None and k in COMPANY_FIELDS},
    )


# --------------------------------------------------------------------------
# backfill runner
# --------------------------------------------------------------------------

_SELECT_BATCH = text("""
    SELECT j.id, j.company_id, s.name AS source_name, d.raw_data,
           j.poster_name, j.poster_title, j.source_applicant_count,
           j.source_view_count, j.apply_email, j.min_exp_years, j.max_exp_years
    FROM jobs j
    JOIN job_sources s ON s.id = j.source_id
    JOIN job_details d ON d.job_id = j.id
    WHERE j.id > :after
      AND d.raw_data IS NOT NULL
      AND s.name = ANY(:sources)
      -- CAST because asyncpg cannot infer a bare NULL parameter's type.
      AND (CAST(:since AS timestamp) IS NULL OR j.first_seen_at >= CAST(:since AS timestamp))
    ORDER BY j.id
    LIMIT :batch
""")

_UPDATE_JOB = """
    UPDATE jobs SET {assignments} WHERE id = :id
"""

# COALESCE keeps whatever is already there — a backfill never overwrites.
_UPDATE_COMPANY = """
    UPDATE companies SET {assignments} WHERE id = :id
"""


async def backfill_from_raw(
    session: AsyncSession,
    *,
    sources: Optional[Iterable[str]] = None,
    since: Optional[datetime] = None,
    batch_size: int = 500,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Fill NULL columns on jobs and companies from stored raw payloads.

    Returns counts of rows scanned and rows actually updated. Company updates
    are coalesced in SQL, so the first source that knows a company's industry
    wins and later sources leave it alone.
    """
    wanted = [s.lower() for s in (sources or SUPPORTED_SOURCES) if s.lower() in EXTRACTORS]
    if not wanted:
        return {"scanned": 0, "jobs_updated": 0, "companies_touched": 0}

    stats = {"scanned": 0, "jobs_updated": 0, "companies_touched": 0}
    company_updates: Dict[int, Dict[str, Any]] = {}
    after = 0

    while True:
        rows = (await session.execute(
            _SELECT_BATCH,
            {"after": after, "sources": wanted, "since": since, "batch": batch_size},
        )).mappings().all()
        if not rows:
            break

        for row in rows:
            after = row["id"]
            stats["scanned"] += 1

            enrichment = extract_enrichment(row["source_name"], row["raw_data"])

            # Only write job columns that are still empty — except the
            # source-authoritative ones, which also correct a stale guess.
            job_changes = {
                k: v for k, v in enrichment.job.items()
                if row.get(k) is None
                or (k in JOB_AUTHORITATIVE_FIELDS and row.get(k) != v)
            }
            if job_changes and not dry_run:
                assignments = ", ".join(f"{k} = :{k}" for k in job_changes)
                await session.execute(
                    text(_UPDATE_JOB.format(assignments=assignments)),
                    {"id": row["id"], **job_changes},
                )
            if job_changes:
                stats["jobs_updated"] += 1

            if row["company_id"] and enrichment.company:
                bucket = company_updates.setdefault(row["company_id"], {})
                for key, value in enrichment.company.items():
                    bucket.setdefault(key, value)

        if not dry_run:
            await session.commit()

        if limit and stats["scanned"] >= limit:
            break

    for company_id, changes in company_updates.items():
        assignments = ", ".join(f"{k} = COALESCE({k}, :{k})" for k in changes)
        if dry_run:
            stats["companies_touched"] += 1
            continue
        result = await session.execute(
            text(_UPDATE_COMPANY.format(assignments=assignments)),
            {"id": company_id, **changes},
        )
        stats["companies_touched"] += result.rowcount or 0

    if not dry_run:
        await session.commit()

    logger.info(
        "Raw backfill: scanned=%s jobs_updated=%s companies_touched=%s sources=%s",
        stats["scanned"], stats["jobs_updated"], stats["companies_touched"], ",".join(wanted),
    )
    return stats
