"""India-specific anti-noise adjustments — score penalties/bonuses, not hard filters.

This is the single biggest quality differentiator versus generic job boards. Applied after the base 0-100 score; the result is clamped
back into [0, 100] by the caller.
"""

import re
from typing import Tuple

from .filters import contains_term, text_blob

STAFFING_SIGNALS = re.compile(
    r"immediate\s*joiner\s*only|\bc2h\b|contract\s*to\s*hire|third\s*party\s*payroll|"
    r"client\s*location|deputation",
    re.IGNORECASE,
)

RIGID_DEGREE_SIGNALS = re.compile(
    r"b\.?tech/?\s*b\.?e\.?\s*in\s*computer\s*science\s*mandatory|"
    r"\b(b\.?tech|b\.?e\.?|degree)\s*(in\s*)?(computer\s*science|cs)\b.{0,15}\b(mandatory|compulsory)|"
    r"computer\s*science\s*degree\s*(is\s*)?mandatory|"
    r"mandatory.{0,20}(b\.?tech|b\.?e\.?|computer\s*science)",
    re.IGNORECASE,
)

# A broad, generic tech list — not tied to any one stack — used only to detect
# "stack spam" (a JD that name-drops far more technologies than one role needs).
STACK_SPAM_KEYWORDS = [
    "java", "python", "node.js", "react", "angular", "vue", "php", "ruby",
    "go", "rust", "c++", "c#", ".net", "django", "flask", "spring", "laravel",
    "aws", "azure", "gcp", "docker", "kubernetes", "jenkins", "terraform",
    "mysql", "postgresql", "mongodb", "redis", "kafka", "rabbitmq",
    "elasticsearch", "graphql", "rest api", "microservices", "hadoop",
    "spark", "tableau", "power bi", "salesforce", "sap", "android", "ios",
    "swift", "kotlin", "flutter", "typescript", "javascript", "html", "css",
]

GHOST_JOB_PENALTY_PER_REPOST = 5
GHOST_JOB_PENALTY_CAP = 15
STACK_SPAM_THRESHOLD = 8
STACK_SPAM_PENALTY = 10
STAFFING_PENALTY = 15
RIGID_DEGREE_PENALTY = 5
DOMAIN_BONUS = 5


def apply_noise_adjustments(base_score: float, job: dict, profile: dict, repost_count: int = 0) -> Tuple[float, dict]:
    """Returns (adjusted_score, factors) — factors go into matches.reasons."""
    blob = text_blob(job)
    factors = {}
    score = base_score

    if STAFFING_SIGNALS.search(blob) and not profile.get("include_staffing", False):
        score -= STAFFING_PENALTY
        factors["staffing_signal"] = -STAFFING_PENALTY

    stack_hits = sum(1 for kw in STACK_SPAM_KEYWORDS if contains_term(kw, blob))
    if stack_hits >= STACK_SPAM_THRESHOLD:
        score -= STACK_SPAM_PENALTY
        factors["stack_spam"] = {"penalty": -STACK_SPAM_PENALTY, "tech_count": stack_hits}

    if repost_count > 0:
        penalty = min(GHOST_JOB_PENALTY_PER_REPOST * repost_count, GHOST_JOB_PENALTY_CAP)
        score -= penalty
        factors["ghost_job_repost"] = {"penalty": -penalty, "repost_count": repost_count}

    if profile.get("no_cs_degree") and RIGID_DEGREE_SIGNALS.search(blob):
        score -= RIGID_DEGREE_PENALTY
        factors["rigid_degree_requirement"] = -RIGID_DEGREE_PENALTY
    if any(contains_term(kw, blob) for kw in profile.get("domain_keywords", [])):
        score += DOMAIN_BONUS
        factors["domain_bonus"] = DOMAIN_BONUS

    return max(0.0, min(100.0, score)), factors
