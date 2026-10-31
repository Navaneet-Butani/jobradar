"""Weighted scoring (0-100) for jobs that survive the hard filters."""

import re
from datetime import datetime, timedelta
from typing import Optional

from rapidfuzz import fuzz

from .filters import contains_term, is_remote_eligible, skill_tokens, text_blob

FRESHNESS_DECAY_DAYS = 21
FRESHNESS_FULL_SCORE_HOURS = 48

TITLE_TOKEN_PATTERN = re.compile(r"[a-z0-9.+#]+")
# Words that carry no discipline signal on their own — "Software Developer"
# and ".Net Developer" share "developer", but that's not a real title match.
# Without stripping these, token_set_ratio scores short titles almost
# entirely on generic-word overlap (observed: "UI Developer" vs ".net
# developer" -> 86, well past the exact-tier threshold).
GENERIC_TITLE_WORDS = {
    "developer", "engineer", "software", "associate", "junior", "senior",
    "sde", "i", "ii", "iii", "iv", "principal", "lead", "full", "stack",
}


def _distinctive_tokens(title: str) -> set:
    return {w for w in TITLE_TOKEN_PATTERN.findall(title) if w not in GENERIC_TITLE_WORDS}

SOURCE_QUALITY = {
    "ats": 5,
    "instahyre": 4,
    "linkedin": 3,
    "indeed": 2,
    "hirist": 4,
    "jobspy": 2,   # Indeed via JobSpy
    "remoteok": 2,
}


def score_skill_overlap(job: dict, profile: dict) -> float:
    """Fraction of must_have_skills present, x35."""
    must_have = [s.lower() for s in profile.get("must_have_skills", [])]
    if not must_have:
        return 35.0
    job_skills = skill_tokens(job)
    blob = text_blob(job)
    present = sum(1 for s in must_have if s in job_skills or contains_term(s, blob))
    return 35.0 * (present / len(must_have))


def score_title_match(job: dict, profile: dict) -> float:
    title = (job.get("normalized_title") or job.get("title") or "").lower()
    if not title:
        return 0.0
    job_distinctive = _distinctive_tokens(title)

    best = 0.0
    for target in profile.get("target_titles", []):
        target_lower = target.lower()
        if target_lower == title:
            return 20.0

        target_distinctive = _distinctive_tokens(target_lower)
        ratio = fuzz.token_set_ratio(target_lower, title)

        if target_distinctive:
            # A specific target ("React Developer", "Next.js Developer")
            # only earns real credit when its distinguishing word actually
            # shows up in the job title — sharing "developer"/"engineer"
            # alone isn't a title match.
            if target_distinctive & job_distinctive:
                best = max(best, 15.0 + 5.0 * min(max(ratio - 60, 0), 40) / 40)
        else:
            # Fully generic target ("Software Developer", "SDE I") — a weak,
            # capped signal so it can never outrank a genuinely specific hit.
            if ratio >= 80:
                best = max(best, 12.0)
            elif ratio >= 60:
                best = max(best, 6.0)

    return min(best, 20.0)


def score_experience_fit(job: dict, profile: dict) -> float:
    years_exp = float(profile["years_exp"])
    min_exp = job.get("min_exp_years")
    max_exp = job.get("max_exp_years")

    if min_exp is None and max_exp is None:
        return 7.0  # unknown — neutral, already passed hard filter

    lo = min_exp if min_exp is not None else max(0, years_exp - 2)
    hi = max_exp if max_exp is not None else years_exp + 1.5

    if lo <= years_exp <= hi:
        span = max(hi - lo, 0.1)
        center = (lo + hi) / 2
        distance_from_center = abs(years_exp - center) / (span / 2)
        return 15.0 if distance_from_center <= 0.5 else 7.0
    return 3.0  # outside [min,max] but within hard-filter tolerance


def score_location_fit(job: dict, profile: dict) -> float:
    city = (job.get("city") or "").lower()
    cities = {c.lower() for c in profile.get("cities", [])}
    metro_cities = {c.lower() for c in profile.get("metro_cities", [])}

    if city in cities:
        return 10.0
    if is_remote_eligible(job, profile):
        return 10.0
    if city in metro_cities:
        return 3.0
    return 0.0


def score_freshness(job: dict) -> float:
    reference = job.get("posted_date") or job.get("first_seen_at")
    if reference is None:
        return 5.0
    if reference.tzinfo is not None:
        now = datetime.now(reference.tzinfo)
    else:
        now = datetime.utcnow()
    age = now - reference
    if age <= timedelta(hours=FRESHNESS_FULL_SCORE_HOURS):
        return 10.0
    if age >= timedelta(days=FRESHNESS_DECAY_DAYS):
        return 0.0
    decay_window = timedelta(days=FRESHNESS_DECAY_DAYS) - timedelta(hours=FRESHNESS_FULL_SCORE_HOURS)
    remaining = timedelta(days=FRESHNESS_DECAY_DAYS) - age
    return 10.0 * (remaining / decay_window)


def score_salary(job: dict, profile: dict) -> float:
    if not job.get("salary_disclosed"):
        return 2.0
    min_salary_inr = profile.get("min_salary_inr")
    if min_salary_inr is None:
        return 5.0
    if job.get("salary_currency") != "INR" or job.get("salary_period") != "year":
        return 2.0  # disclosed but not directly comparable
    job_salary = job.get("salary_max") or job.get("salary_min")
    if job_salary is None:
        return 2.0
    return 5.0 if float(job_salary) >= float(min_salary_inr) else 0.0


def score_source_quality(job: dict) -> float:
    return SOURCE_QUALITY.get(job.get("source_name", ""), 2.0)


def score_job(job: dict, profile: dict) -> dict:
    """Compute the full weighted breakdown. Returns {'total': float, 'breakdown': {...}}."""
    breakdown = {
        "skill_overlap": round(score_skill_overlap(job, profile), 2),
        "title_match": round(score_title_match(job, profile), 2),
        "experience_fit": round(score_experience_fit(job, profile), 2),
        "location_fit": round(score_location_fit(job, profile), 2),
        "freshness": round(score_freshness(job), 2),
        "salary": round(score_salary(job, profile), 2),
        "source_quality": round(score_source_quality(job), 2),
    }
    total = sum(breakdown.values())
    return {"total": total, "breakdown": breakdown}
