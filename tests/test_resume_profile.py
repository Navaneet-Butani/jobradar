"""Resume -> profile suggestion: heuristics without AI, validated LLM overlay."""
import asyncio

from app.services.resume_profile import merge_llm, suggest_profile

RESUME = """Asha Verma - Senior Backend Engineer, Pune, India
Backend developer with 7+ years of experience in Python and Node.js.
Senior Backend Engineer at Acme: Python, FastAPI, Django, PostgreSQL, Redis, AWS, Docker.
Software Engineer at Example Labs, Bengaluru: React, TypeScript, Python."""


def test_heuristic_suggestion_without_llm():
    out = asyncio.run(suggest_profile(RESUME))
    s = out["suggestion"]
    assert out["source"] == "heuristic"
    assert s["years_exp"] == 7.0
    assert "python" in s["must_have_skills"]
    assert {"Pune", "Bengaluru"} <= set(s["cities"])
    assert "Senior Backend Engineer" in s["target_titles"]


def test_llm_overlay_is_validated():
    base = {"years_exp": 7.0, "must_have_skills": ["python"], "nice_to_have_skills": [],
            "target_titles": ["Backend Developer"], "cities": ["Pune"]}
    out = merge_llm(base, {"years_exp": "99", "must_have_skills": ["Go", "Rust"],
                           "target_titles": ["staff engineer"], "cities": "not a list"})
    assert out["years_exp"] == 7.0                 # out of range ignored
    assert out["must_have_skills"] == ["go", "rust"]
    assert out["target_titles"] == ["Staff Engineer"]
    assert out["cities"] == ["Pune"]               # invalid type ignored
    assert merge_llm(base, None) == base
