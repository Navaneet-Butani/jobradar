"""Fast, DB-free checks on the matching rules. Run: pytest -q"""
from datetime import datetime, timedelta

from app.services.matching.filters import contains_term, passes_hard_filters
from app.services.matching.noise import apply_noise_adjustments
from app.services.matching.scoring import score_job
from app.services.role_filter import is_it_role
from app.services.search_targets import SearchTargets, _dedupe

PROFILE = {
    "years_exp": 4, "must_have_skills": ["react"], "target_titles": ["Frontend Developer"],
    "cities": ["Pune"], "metro_cities": ["Mumbai"], "accepts_remote": True, "remote_only": False,
    "exclude_keywords": ["java"], "exclude_companies": ["Bad Corp"], "include_staffing": False,
    "domain_keywords": [], "no_cs_degree": False, "min_salary_inr": None,
}


def job(**kw):
    base = {"title": "Frontend Developer", "description": "Build React apps.", "city": "Pune",
            "is_remote": False, "company_name": "Good Co", "min_exp_years": 3, "max_exp_years": 6,
            "posted_date": datetime.utcnow() - timedelta(hours=5), "skills_extracted": ["react"]}
    base.update(kw)
    return base


def test_contains_term_is_whole_word():
    assert contains_term("go", "we use go and rust")
    assert not contains_term("go", "a good team, two years ago")
    assert not contains_term("java", "modern javascript")
    assert not contains_term("sap", "join asap")
    assert contains_term("c++", "strong c++ skills")
    assert contains_term(".net", "experience with .net core")
    assert contains_term("node.js", "node.js backend")


def test_stack_spam_ignores_substring_lookalikes():
    blob = "good team, javascript, asap joining, reactive scenarios and ratios"
    _, factors = apply_noise_adjustments(80, job(description=blob), PROFILE)
    assert "stack_spam" not in factors


def test_excluded_keyword_does_not_hit_javascript_jobs():
    ok, reason = passes_hard_filters(job(description="React and JavaScript, TypeScript."), PROFILE)
    assert ok, reason


def test_hard_filters_drop_wrong_city_excluded_company_and_seniority():
    assert not passes_hard_filters(job(city="Kolkata"), PROFILE)[0]
    assert not passes_hard_filters(job(company_name="Bad Corp"), PROFILE)[0]
    assert not passes_hard_filters(job(min_exp_years=9, max_exp_years=12), PROFILE)[0]


def test_metro_city_needs_hybrid_signal():
    assert not passes_hard_filters(job(city="Mumbai"), PROFILE)[0]
    assert passes_hard_filters(job(city="Mumbai", description="React. Hybrid, 2 days in office."), PROFILE)[0]


def test_remote_scope():
    assert passes_hard_filters(job(city="", is_remote=True, remote_scope="india_only"), PROFILE)[0]
    assert not passes_hard_filters(job(city="", is_remote=True, remote_scope="us_only"), PROFILE)[0]


def test_profile_hints_are_profile_fields():
    rigid = job(description="React. B.Tech in Computer Science mandatory. Fintech payments.")
    base, _ = apply_noise_adjustments(70, rigid, PROFILE)
    adjusted, factors = apply_noise_adjustments(
        70, rigid, {**PROFILE, "no_cs_degree": True, "domain_keywords": ["fintech"]})
    assert factors["rigid_degree_requirement"] < 0 and factors["domain_bonus"] > 0
    assert adjusted == base  # -5 penalty, +5 bonus


def test_score_is_bounded_and_explained():
    result = score_job(job(), PROFILE)
    assert 0 <= result["total"] <= 100
    assert set(result["breakdown"]) >= {"skill_overlap", "title_match", "location_fit", "freshness"}


def test_role_filter_allowlist():
    assert is_it_role("Senior Backend Engineer")
    assert not is_it_role("Consultor(A) Comercial Externo")
    assert not is_it_role("Retail Store Manager")


def test_search_targets_helpers():
    assert _dedupe(["Pune", "pune ", "Mumbai", ""], 5) == ["Pune", "Mumbai"]
    assert SearchTargets().locations(["Pune", "Austin, TX"]) == ["Pune, India", "Austin, TX"]


def test_city_spellings_are_one_city():
    from app.services.matching.filters import canonical_city
    assert canonical_city("Bangalore") == canonical_city("Bengaluru") == "bengaluru"
    assert canonical_city("Hosur Road Bangalore") == "bengaluru"
    assert canonical_city("Gurgaon") == "gurugram"
    assert canonical_city("Coimbatore") == "coimbatore"
    profile = {**PROFILE, "cities": ["Bengaluru"]}
    assert passes_hard_filters(job(city="Bangalore"), profile)[0]
    assert score_job(job(city="Bangalore"), profile)["breakdown"]["location_fit"] == 10
