"""Hard filters — drop the job entirely before scoring. Cheap, removes most rows."""

import re
from functools import lru_cache
from typing import Optional, Tuple

ACCEPTED_REMOTE_SCOPES = {"india_only", "global"}

HYBRID_SIGNALS = re.compile(
    r"hybrid|\d+\s*days?\s*(from|in|at)\s*(the\s*)?office|work\s*from\s*anywhere|"
    r"remote[\s-]friendly|remote[\s-]first|occasional\s*travel\s*to\s*office",
    re.IGNORECASE,
)

# A seniority ceiling of 'mid' rejects postings clearly
# aimed at 5+ yr candidates.
SENIORITY_CEILING_MIN_YEARS = {"mid": 5}


def text_blob(job: dict) -> str:
    return f"{job.get('title', '')} {job.get('description', '') or ''}".lower()


@lru_cache(maxsize=4096)
def _term_pattern(term: str) -> re.Pattern:
    # Boundaries only on alphanumeric ends, so "c++", ".net" and "node.js" still
    # work while "go" no longer matches "good" and "java" no longer matches
    # "javascript" (plain substring checks did both).
    prefix = r"(?<![a-z0-9])" if term[:1].isalnum() else ""
    suffix = r"(?![a-z0-9])" if term[-1:].isalnum() else ""
    return re.compile(prefix + re.escape(term) + suffix)


def contains_term(term: str, blob: str) -> bool:
    """Whole-word match of a lowercase term inside a lowercase text blob."""
    term = term.strip().lower()
    return bool(term) and _term_pattern(term).search(blob) is not None


# Spellings that refer to the same city. Sources disagree ("Bangalore" vs
# "Bengaluru", "Gurgaon" vs "Gurugram") and some put an area first ("Hosur Road
# Bangalore"), so cities are compared by canonical name, never as raw strings.
CITY_ALIASES = {
    "bengaluru": ["bangalore", "bengaluru", "blr"],
    "mumbai": ["mumbai", "bombay", "navi mumbai", "thane"],
    "delhi": ["delhi", "new delhi", "delhi ncr", "ncr"],
    "gurugram": ["gurugram", "gurgaon"],
    "noida": ["noida", "greater noida"],
    "chennai": ["chennai", "madras"],
    "kolkata": ["kolkata", "calcutta"],
    "pune": ["pune", "poona"],
    "vadodara": ["vadodara", "baroda"],
    "mysuru": ["mysuru", "mysore"],
    "thiruvananthapuram": ["thiruvananthapuram", "trivandrum"],
    "kochi": ["kochi", "cochin"],
    "hyderabad": ["hyderabad", "secunderabad"],
    "ahmedabad": ["ahmedabad", "amdavad"],
}
_ALIAS_TO_CITY = {alias: canonical for canonical, aliases in CITY_ALIASES.items() for alias in aliases}


def canonical_city(name: Optional[str]) -> str:
    """'Hosur Road Bangalore' -> 'bengaluru'; unknown cities come back lowercased."""
    text = (name or "").strip().lower()
    if not text:
        return ""
    if text in _ALIAS_TO_CITY:
        return _ALIAS_TO_CITY[text]
    for alias, canonical in _ALIAS_TO_CITY.items():
        if contains_term(alias, text):
            return canonical
    return text


def city_spellings(name: str) -> list:
    """Every spelling of a city, for matching it in SQL."""
    canonical = canonical_city(name)
    return CITY_ALIASES.get(canonical, [canonical]) if canonical else []


def skill_tokens(job: dict) -> set:
    tokens = set()
    for s in job.get("skills_extracted") or []:
        if isinstance(s, str):
            tokens.add(s.lower())
    return tokens


def is_remote_eligible(job: dict, profile: dict) -> bool:
    if not job.get("is_remote"):
        return False
    if not profile.get("accepts_remote", True):
        return False
    scope = job.get("remote_scope")
    # Unclassified remote scope: don't punish the job for missing data, but
    # don't treat it as a free pass either — only explicit accepted scopes count.
    return scope in ACCEPTED_REMOTE_SCOPES


def check_location(job: dict, profile: dict) -> Tuple[bool, Optional[str]]:
    city = (job.get("city") or "").strip()
    cities = {canonical_city(c) for c in profile.get("cities", [])}
    metro_cities = {canonical_city(c) for c in profile.get("metro_cities", [])}
    city_lower = canonical_city(city)

    remote_eligible = is_remote_eligible(job, profile)

    if profile.get("remote_only") and not remote_eligible:
        return False, "remote_only profile, job not remote-eligible"

    if city_lower in cities:
        return True, None

    if remote_eligible:
        return True, None

    if city_lower in metro_cities:
        if HYBRID_SIGNALS.search(text_blob(job)):
            return True, None
        return False, f"metro city '{city}' without hybrid/remote-friendly signal"

    return False, f"city '{city}' not in cities/metro_cities and not remote-eligible"


def check_remote_scope(job: dict, profile: dict) -> Tuple[bool, Optional[str]]:
    """A us_only/eu_only/uk_only remote job is dropped outright, regardless of city fields."""
    if job.get("is_remote") and job.get("remote_scope") not in (None, *ACCEPTED_REMOTE_SCOPES):
        return False, f"remote_scope '{job.get('remote_scope')}' rejected"
    return True, None


def check_experience(job: dict, profile: dict) -> Tuple[bool, Optional[str]]:
    years_exp = float(profile["years_exp"])
    min_exp = job.get("min_exp_years")
    max_exp = job.get("max_exp_years")

    if min_exp is not None and min_exp > years_exp + 1.5:
        return False, f"job min_exp_years={min_exp} exceeds profile years_exp+1.5"
    if max_exp is not None and max_exp < years_exp - 2:
        return False, f"job max_exp_years={max_exp} below profile years_exp-2 (overqualified)"

    ceiling = profile.get("seniority_ceiling")
    ceiling_min_years = SENIORITY_CEILING_MIN_YEARS.get(ceiling) if ceiling else None
    if ceiling_min_years is not None and min_exp is not None and min_exp >= ceiling_min_years:
        return False, f"job min_exp_years={min_exp} exceeds seniority_ceiling '{ceiling}'"

    return True, None


def check_excluded_keywords(job: dict, profile: dict) -> Tuple[bool, Optional[str]]:
    blob = text_blob(job)
    for kw in profile.get("exclude_keywords", []):
        if contains_term(kw, blob):
            return False, f"excluded keyword '{kw}'"
    return True, None


def check_excluded_companies(job: dict, profile: dict) -> Tuple[bool, Optional[str]]:
    company = (job.get("company_name") or "").lower()
    for excluded in profile.get("exclude_companies", []):
        if excluded.lower() == company:
            return False, f"excluded company '{job.get('company_name')}'"
    return True, None


def check_must_have_skills(job: dict, profile: dict) -> Tuple[bool, Optional[str]]:
    must_have = [s.lower() for s in profile.get("must_have_skills", [])]
    if not must_have:
        return True, None
    job_skills = skill_tokens(job)
    blob = text_blob(job)
    for skill in must_have:
        if skill in job_skills or contains_term(skill, blob):
            return True, None
    return False, f"none of must_have_skills {must_have} present"


HARD_FILTERS = [
    check_remote_scope,
    check_location,
    check_experience,
    check_excluded_keywords,
    check_excluded_companies,
    check_must_have_skills,
]


def passes_hard_filters(job: dict, profile: dict) -> Tuple[bool, Optional[str]]:
    """Run every hard filter; return (passes, reason) — reason is set only on drop."""
    for filter_fn in HARD_FILTERS:
        passed, reason = filter_fn(job, profile)
        if not passed:
            return False, reason
    return True, None
