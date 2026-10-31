"""Optional LLM re-rank pass — Gemini Flash free tier.

Blends a 0-10 relevance score and a one-line "why this fits" into the rule
score. Must degrade gracefully: if GEMINI_API_KEY is absent or any call
fails, callers get the rule score back unchanged and no explanation —
never block the feed on this.
"""

import asyncio
import logging
from typing import List, Optional, Tuple

import httpx

from ..llm.gemini import generate_json, is_enabled, SECONDS_BETWEEN_CALLS

logger = logging.getLogger(__name__)

DESCRIPTION_EXCERPT_CHARS = 1500
RULE_WEIGHT = 0.7
LLM_WEIGHT = 0.3


def _build_prompt(job: dict, profile_summary: str) -> str:
    description = (job.get("description") or "")[:DESCRIPTION_EXCERPT_CHARS]
    return (
        "You are screening a job posting for a specific candidate. "
        "Rate how well this job fits the candidate from 0 (not a fit) to 10 (excellent fit), "
        "and give one short sentence explaining why, written to the candidate directly.\n\n"
        f"Candidate profile: {profile_summary}\n\n"
        f"Job title: {job.get('title', '')}\n"
        f"Company: {job.get('company_name', '')}\n"
        f"Job description (excerpt): {description}\n\n"
        'Respond with strict JSON only: {"relevance_score": <0-10 number>, "why": "<one sentence>"}'
    )


def _profile_summary(profile: dict) -> str:
    parts = [f"{profile['years_exp']} years experience"]
    if profile.get("must_have_skills"):
        parts.append("core skills: " + ", ".join(profile["must_have_skills"]))
    if profile.get("target_titles"):
        parts.append("targeting titles like: " + ", ".join(profile["target_titles"][:5]))
    return "; ".join(parts)


async def rerank_one(job: dict, profile: dict, client: httpx.AsyncClient) -> Optional[Tuple[float, str]]:
    """Returns (relevance_score_0_10, why_sentence), or None on any failure."""
    prompt = _build_prompt(job, _profile_summary(profile))
    parsed = await generate_json(prompt, client)
    if parsed is None:
        return None
    try:
        score = float(parsed["relevance_score"])
        why = str(parsed["why"]).strip()
        return score, why
    except (KeyError, ValueError, TypeError) as e:
        logger.warning(f"LLM re-rank malformed response for job {job.get('id')}: {e}")
        return None


async def rerank_top_matches(scored_matches: List[dict], profile: dict, top_n: int = 25) -> List[dict]:
    """Re-rank the top N matches (by rule score) with an LLM pass.

    scored_matches: list of {'job': dict, 'score': float, 'breakdown': dict}
    sorted by score descending. Mutates and returns the same list — matches
    outside top_n, or any that fail/skip the LLM call, keep their rule score
    and no explanation.
    """
    if not is_enabled() or not scored_matches:
        return scored_matches

    top_slice = scored_matches[:top_n]
    async with httpx.AsyncClient() as client:
        for i, match in enumerate(top_slice):
            if i > 0:
                await asyncio.sleep(SECONDS_BETWEEN_CALLS)

            result = await rerank_one(match["job"], profile, client)
            if result is None:
                continue
            llm_score, why = result
            match["score"] = round(RULE_WEIGHT * match["score"] + LLM_WEIGHT * (llm_score * 10), 2)
            match["explanation"] = why
            match["breakdown"]["llm_relevance"] = llm_score

    return scored_matches
