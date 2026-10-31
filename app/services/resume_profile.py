"""Suggest job-profile fields from a resume.

Two layers, so it works without any AI configured:
  1. Heuristics: skills from SkillExtractor (ranked by how often the resume
     mentions them), years of experience from "6+ years" style phrases, role
     titles from a title pattern, Indian cities the location parser knows.
  2. If an LLM is configured, it refines the result; anything it returns
     that fails validation falls back to the heuristic value.

Nothing is saved: the caller shows the suggestion in the profile form and the
user edits and saves it.
"""

import json
import re
from collections import Counter
from typing import Dict, List, Optional

import httpx

from ..models.job import SkillCategory
from .matching.filters import contains_term
from .llm.gemini import generate_json, is_enabled
from .location_parser import LocationParser
from .skill_extractor import SkillExtractor

TECH_CATEGORIES = {
    SkillCategory.PROGRAMMING_LANGUAGE, SkillCategory.FRAMEWORK, SkillCategory.DATABASE,
    SkillCategory.CLOUD_PLATFORM, SkillCategory.TOOL,
}
CORE_CATEGORIES = {SkillCategory.PROGRAMMING_LANGUAGE, SkillCategory.FRAMEWORK}

YEARS_PATTERN = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
TITLE_PATTERN = re.compile(
    r"\b((?:senior|sr\.?|lead|staff|principal|junior|jr\.?|associate)?\s*"
    r"(?:software|backend|back-end|frontend|front-end|full[- ]?stack|mobile|android|ios|web|"
    r"devops|data|ml|machine learning|qa|test|cloud|platform|python|java|react|node(?:\.?js)?)\s+"
    r"(?:engineer|developer|architect|lead))\b",
    re.IGNORECASE,
)
DISPLAY_CITY = {"bangalore": "Bengaluru", "delhi": "Delhi NCR"}
RESUME_CHARS_FOR_LLM = 6000


def _years(text: str) -> Optional[float]:
    values = [float(m) for m in YEARS_PATTERN.findall(text) if 0 < float(m) <= 40]
    return max(values) if values else None


def _titles(text: str) -> List[str]:
    counts = Counter(re.sub(r"\s+", " ", t).strip().title() for t in TITLE_PATTERN.findall(text))
    return [t for t, _ in counts.most_common(6)]


def _cities(text: str) -> List[str]:
    lowered = text.lower()
    found = []
    for city, info in LocationParser.MAJOR_CITIES.items():
        if info.get("country") != "India":
            continue
        names = [city, *info.get("aliases", [])]
        if any(contains_term(n, lowered) for n in names):
            found.append(DISPLAY_CITY.get(city, city.title()))
    return found[:5]


async def _skills(text: str) -> Dict[str, List[str]]:
    lowered = text.lower()
    extracted = [s for s in await SkillExtractor().extract_skills(text) if s.category in TECH_CATEGORIES]
    mentions = {s.name: len(re.findall(re.escape(s.name), lowered)) or 1 for s in extracted}
    ranked = sorted(extracted, key=lambda s: (-mentions[s.name], s.name))
    core = [s.name for s in ranked if s.category in CORE_CATEGORIES][:3]
    rest = [s.name for s in ranked if s.name not in core][:12]
    return {"must_have_skills": core, "nice_to_have_skills": rest}


def heuristic_suggestion(text: str, skills: Dict[str, List[str]]) -> dict:
    return {
        "years_exp": _years(text),
        "target_titles": _titles(text),
        "cities": _cities(text),
        **skills,
    }


def _str_list(value, limit: int) -> Optional[List[str]]:
    if not isinstance(value, list):
        return None
    out = [str(v).strip() for v in value if isinstance(v, (str, int, float)) and str(v).strip()]
    return out[:limit] or None


def merge_llm(base: dict, llm: Optional[dict]) -> dict:
    """Overlay validated LLM fields on the heuristic suggestion."""
    if not isinstance(llm, dict):
        return base
    merged = dict(base)
    try:
        years = float(llm.get("years_exp"))
        if 0 <= years <= 40:
            merged["years_exp"] = round(years, 1)
    except (TypeError, ValueError):
        pass
    for key, limit in (("must_have_skills", 5), ("nice_to_have_skills", 15),
                       ("target_titles", 8), ("cities", 5)):
        value = _str_list(llm.get(key), limit)
        if value:
            if key.endswith("skills"):
                merged[key] = [v.lower() for v in value]
            else:  # titles and cities: keep the model's casing unless it sent all-lowercase
                merged[key] = [v if v != v.lower() else v.title() for v in value]
    return merged


def _prompt(text: str) -> str:
    return (
        "Read this resume and suggest a job-search profile for this candidate. Reply with ONLY a JSON object:\n"
        '{"years_exp": number, "must_have_skills": [3-5 core technologies they would require in a job], '
        '"nice_to_have_skills": [up to 12 other technologies], '
        '"target_titles": [5-8 job titles they should search for, at their seniority], '
        '"cities": [Indian cities they live in or mention as preferred]}\n'
        "Use lowercase skill names. Do not invent anything not supported by the resume.\n\n"
        f"Resume:\n{text[:RESUME_CHARS_FOR_LLM]}"
    )


async def suggest_profile(resume_text: str) -> dict:
    skills = await _skills(resume_text)
    suggestion = heuristic_suggestion(resume_text, skills)
    source = "heuristic"
    if is_enabled():
        async with httpx.AsyncClient() as client:
            llm = await generate_json(_prompt(resume_text), client, max_output_tokens=500)
        if llm:
            suggestion, source = merge_llm(suggestion, llm), "llm"
    return {"source": source, "suggestion": suggestion}


if __name__ == "__main__":  # quick manual check: python -m app.services.resume_profile resume.txt
    import asyncio
    import sys

    print(json.dumps(asyncio.run(suggest_profile(open(sys.argv[1], encoding="utf-8").read())), indent=2))
