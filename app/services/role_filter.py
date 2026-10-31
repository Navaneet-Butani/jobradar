"""Which job titles count as roles we want to scrape.

Used by source adapters that cannot ask their upstream for a role filter.
Instahyre, Hirist and JobSpy all query by keyword, so what they return is
already in scope; the ATS adapter walks whole Greenhouse/Lever/Ashby boards
and takes every posting, which is how recruiters, account executives and
Brazilian field-sales agents ended up in the corpus. Measured on one real ATS
run: 1,948 postings, of which 526 were not IT roles at all.

The rule is an allowlist, deliberately. A denylist was tried first and kept
91% of that run, because the junk is multilingual -- "Consultor(A) Comercial
Externo", "Executivo(A) De Contas" -- and no English stop-list catches it.
Requiring a positive signal instead keeps 73%, and what it drops is uniformly
sales, finance, legal and HR.

Which categories are active is configuration, not code: see
`app/services/scraping_config.py`, which reads the enabled set from
system_settings and is edited from the UI. A title survives only if it matches
an ENABLED category, so turning a category off genuinely stops collecting it.
"""

import re
from typing import Dict, Iterable, List, Optional

# key -> label, title patterns, and the search terms keyword-driven sources
# (JobSpy, LinkedIn) should query for when the category is enabled.
#
# Patterns are word-boundary anchored where a substring would misfire: \bai\b
# so it does not match "Retail", \bit\b so it does not match "Recruit".
ROLE_CATEGORIES: Dict[str, dict] = {
    "backend": {
        "label": "Backend Engineering",
        "patterns": [r"back.?end", r"\bapi\b", r"microservice", r"node", r"python",
                     r"\bjava\b", r"golang", r"ruby", r"\bphp\b", r"\.net", r"dotnet",
                     r"server.?side"],
        "terms": ["backend developer", "node js developer", "python developer"],
    },
    "frontend": {
        "label": "Frontend Engineering",
        "patterns": [r"front.?end", r"react", r"angular", r"\bvue\b", r"javascript",
                     r"typescript", r"web developer", r"\bui developer\b"],
        "terms": ["react developer", "frontend developer", "next js developer"],
    },
    "fullstack": {
        "label": "Full-Stack Engineering",
        "patterns": [r"full.?stack", r"software engineer", r"software developer",
                     r"\bsde\b", r"\bswe\b", r"programmer", r"member of technical staff"],
        "terms": ["full stack developer", "senior software engineer"],
    },
    "mobile": {
        "label": "Mobile (iOS / Android)",
        "patterns": [r"mobile", r"\bios\b", r"android", r"flutter", r"react native",
                     r"kotlin", r"swift"],
        "terms": ["android developer", "ios developer"],
    },
    "qa": {
        "label": "QA & Test Automation",
        "patterns": [r"\bqa\b", r"quality assurance", r"\bsdet\b", r"tester",
                     r"\btest\b", r"test automation", r"automation engineer"],
        "terms": ["qa engineer", "automation test engineer"],
    },
    "devops": {
        "label": "DevOps / SRE / Cloud",
        "patterns": [r"devops", r"\bsre\b", r"site reliability", r"platform engineer",
                     r"infrastructure", r"cloud", r"kubernetes", r"release engineer",
                     r"build engineer"],
        "terms": ["devops engineer", "cloud engineer"],
    },
    "data": {
        "label": "Data / ML / AI",
        "patterns": [r"data scien", r"data engineer", r"data analyst",
                     r"analytics engineer", r"machine learning", r"\bml\b", r"\bai\b",
                     r"\bllm\b", r"data center", r"data centre"],
        "terms": ["data engineer", "machine learning engineer"],
    },
    "security": {
        "label": "Security Engineering",
        "patterns": [r"security engineer", r"cyber", r"infosec", r"appsec",
                     r"penetration test"],
        "terms": ["security engineer"],
    },
    "design": {
        "label": "UI / UX & Graphics",
        "patterns": [r"\bui\b", r"\bux\b", r"ui/ux", r"graphic", r"product design",
                     r"web design", r"visual design", r"design system", r"motion design"],
        "terms": ["ui ux designer"],
    },
    "it_support": {
        "label": "IT Support & Sysadmin",
        "patterns": [r"\bit\b", r"help ?desk", r"service desk", r"technical support",
                     r"support engineer", r"sysadmin", r"system administrator",
                     r"database administrator", r"\bdba\b", r"network engineer",
                     r"technician"],
        "terms": ["it support engineer"],
    },
    "architect": {
        "label": "Architecture & Tech Lead",
        "patterns": [r"architect", r"tech lead", r"technical lead", r"\bcto\b",
                     r"principal engineer", r"staff engineer", r"engineering manager"],
        "terms": ["software architect"],
    },
    "embedded": {
        "label": "Embedded & Firmware",
        "patterns": [r"embedded", r"firmware", r"\brtos\b", r"device driver"],
        "terms": ["embedded engineer"],
    },
    "product_tech": {
        "label": "Technical Product / Program",
        "patterns": [r"technical program", r"technical product", r"scrum master",
                     r"solutions engineer"],
        "terms": [],
    },
}

# Everything on, which is the behaviour before this became configurable.
DEFAULT_ENABLED: List[str] = list(ROLE_CATEGORIES)

# A bare "engineer"/"developer" with no other signal — e.g. "Engineer II" — is
# still an engineering job, so it is kept whenever any engineering category is
# on. Kept out of the category patterns so that disabling, say, `design` does
# not accidentally take these with it.
_GENERIC_ENGINEERING = re.compile(r"developer|engineer|engineering|software", re.IGNORECASE)
_ENGINEERING_KEYS = {"backend", "frontend", "fullstack", "mobile", "qa", "devops",
                     "data", "security", "it_support", "architect", "embedded"}

_COMPILED = {k: re.compile("|".join(v["patterns"]), re.IGNORECASE)
             for k, v in ROLE_CATEGORIES.items()}


def categories_for(title: str) -> List[str]:
    """Every enabled-or-not category whose patterns the title matches."""
    if not title:
        return []
    return [k for k, rx in _COMPILED.items() if rx.search(title)]


def is_it_role(title: str, enabled: Optional[Iterable[str]] = None) -> bool:
    """True when the title matches at least one enabled category.

    `enabled` defaults to every category. An empty title is kept: there is
    nothing to judge on, and the matching engine still gets to reject it later
    — dropping here would lose the job permanently.
    """
    if not title:
        return True
    keys = set(DEFAULT_ENABLED if enabled is None else enabled)
    if not keys:
        return True  # nothing configured: do not silently collect nothing
    if any(_COMPILED[k].search(title) for k in keys if k in _COMPILED):
        return True
    return bool(keys & _ENGINEERING_KEYS) and bool(_GENERIC_ENGINEERING.search(title))


def search_terms_for(enabled: Optional[Iterable[str]] = None) -> List[str]:
    """Keyword-source search terms for the enabled categories, de-duplicated."""
    keys = DEFAULT_ENABLED if enabled is None else list(enabled)
    seen, out = set(), []
    for k in keys:
        for t in ROLE_CATEGORIES.get(k, {}).get("terms", []):
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


def _demo() -> None:
    """Self-check against titles taken verbatim from a real ATS run."""
    keep = [
        "Senior Software Engineer", "Backend Developer", "React Developer",
        "QA Automation Engineer", "UI/UX Designer", "Graphic Designer",
        "Director Of Product Design", "IT Support Specialist(Temp)",
        "IT Team Lead", "Data Center Technician", "Site Reliability Engineer",
        "Staff Ciam Security Engineer", "Principal Backend Engineer",
        "Solutions Architect - Backend (Agentic Ai & Python)",
        "Member Of Technical Staff, Platform", "Engineer II",
    ]
    drop = [
        "Account Executive | Strategic", "Senior Recruiter | G&A",
        "Channel Partner Manager | Accounting", "Event Marketing Manager",
        "Senior Financial Crimes Compliance Controls Strategist",
        "Sales Development Representative | Inbound",
        "Agente Stone - Consultor(A) Comercial Externo | Santos/Sp",
        "Equity Research Analyst (Amc)", "Accounting Manager",
    ]
    for t in keep:
        assert is_it_role(t), f"should have been kept: {t}"
    for t in drop:
        assert not is_it_role(t), f"should have been dropped: {t}"
    assert is_it_role("") and is_it_role(None)

    # Turning a category off must actually stop collecting it.
    only_backend = ["backend"]
    assert is_it_role("Backend Developer", only_backend)
    assert not is_it_role("Graphic Designer", only_backend), "design should be off"
    assert is_it_role("Graphic Designer", ["design"])
    # Generic engineering follows the engineering categories, not design.
    assert not is_it_role("Engineer II", ["design"])
    assert is_it_role("Engineer II", ["backend"])
    assert "backend" in categories_for("Node Js Backend Developer")
    assert search_terms_for(["security"]) == ["security engineer"]
    print(f"role_filter OK — {len(keep)} kept, {len(drop)} dropped, toggles honoured")


if __name__ == "__main__":
    _demo()
