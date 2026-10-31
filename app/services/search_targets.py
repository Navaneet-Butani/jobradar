"""What the keyword-driven scrapers (JobSpy, LinkedIn, Hirist) search for.

Derived from the people using the deployment, not hardcoded: the union of every
active job profile's cities and target titles. A fresh install with no
profiles yet falls back to India's main tech hubs and the search terms of the
enabled role categories (Settings -> Scraping), so the first ingest still
returns something useful.
"""

from dataclasses import dataclass, field
from typing import List

from sqlalchemy import select

from ..core.database import db
from ..models import JobProfileDB
from .role_filter import ROLE_CATEGORIES
from .scraping_config import get_enabled_categories

DEFAULT_CITIES = ["Bengaluru", "Hyderabad", "Pune", "Chennai", "Mumbai", "Gurugram", "Noida"]

# ponytail: hard caps keep one run inside the free Actions/runtime budget
# (searches = cities x terms). Raise them if you self-host on a bigger box.
MAX_CITIES = 8
MAX_TERMS = 12


@dataclass
class SearchTargets:
    cities: List[str] = field(default_factory=list)        # onsite cities, highest priority
    metro_cities: List[str] = field(default_factory=list)  # hybrid-acceptable cities, searched last
    terms: List[str] = field(default_factory=list)

    def locations(self, cities: List[str]) -> List[str]:
        """City names as job boards expect them ("Pune, India")."""
        return [c if "," in c else f"{c}, India" for c in cities]


def _dedupe(values, limit: int) -> List[str]:
    seen, out = set(), []
    for v in values:
        key = (v or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(v.strip())
    return out[:limit]


async def load_search_targets() -> SearchTargets:
    async with db.get_session() as session:
        profiles = (
            await session.execute(select(JobProfileDB).where(JobProfileDB.is_active.is_(True)))
        ).scalars().all()
        enabled = await get_enabled_categories(session)

    cities = _dedupe((c for p in profiles for c in (p.cities or [])), MAX_CITIES)
    metro = [c for c in _dedupe((c for p in profiles for c in (p.metro_cities or [])), MAX_CITIES)
             if c.lower() not in {x.lower() for x in cities}]
    terms = _dedupe((t for p in profiles for t in (p.target_titles or [])), MAX_TERMS)

    if not terms:
        terms = _dedupe((t for k in enabled for t in ROLE_CATEGORIES[k].get("terms", [])), MAX_TERMS)
    if not cities and not metro:
        cities = list(DEFAULT_CITIES)
    return SearchTargets(cities=cities, metro_cities=metro, terms=terms)
