"""LinkedIn source configuration.

Replaces JobSpy's LinkedIn scraper, which is still installed for Indeed.
Two reasons for going direct:

  1. JobSpy pages the guest endpoint with `start += 25` against a response
     that carries 10 cards, so it never sees ~60% of any result set.
  2. It caps at `results_wanted` per search with no notion of a per-run
     request budget, which is the only control that matters when the risk
     being managed is "how hard did we hit LinkedIn today".

Cities and search terms come from the active job profiles
(app/services/search_targets.py), shared with JobSpy and Hirist.
"""

import logging
from typing import List, NamedTuple, Optional, Tuple

from ...models.source import SourceConfig, FieldMapping, ExtractionRules
from ...repositories.source_repository import SourceRepository
from ...services.search_targets import SearchTargets
from .client import LINKEDIN_SEARCH_URL, test_linkedin_connection

logger = logging.getLogger(__name__)

# Maps the dicts produced by client._parse_cards, not LinkedIn's own field names.
LINKEDIN_FIELD_MAPPING = FieldMapping(
    title=["title"],
    company=["company"],
    location=["location"],
    apply_url=["job_url"],
    posted_date=["posted_at"],
    salary=["salary"],
)

REMOTE_LOCATION = "India"


class ValidationResult(NamedTuple):
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    connection_test: bool


def search_matrix(targets: SearchTargets) -> List[Tuple[Optional[str], str]]:
    """(city, term) pairs in priority order: primary cities first, then
    India-remote, then the hybrid-acceptable metros. Same ordering rationale as JobSpy's — a run's budget is
    always smaller than the matrix, so the order decides what gets covered.
    """
    terms = targets.terms
    ordered: List[Tuple[Optional[str], str]] = [
        (city, term) for city in targets.locations(targets.cities) for term in terms]
    ordered += [(None, term) for term in terms]                      # India-remote sweep
    ordered += [(city, term) for city in targets.locations(targets.metro_cities) for term in terms]
    return ordered


async def setup_linkedin_source() -> int:
    """Register (or update) the LinkedIn source row. Returns the source_id."""
    source_repo = SourceRepository()

    source_data = {
        'name': 'linkedin',
        'type': 'scraping',
        'base_url': LINKEDIN_SEARCH_URL,
        'is_active': True,
        # 1 request / 3s -> 1,200/hour ceiling; the per-run budget in the
        # fetcher is the control that actually binds.
        'hourly_quota': 1200,
        'daily_quota': 3000,
        'monthly_quota': 90000,
        'cost_per_call': 0.0000,
        'monthly_budget': 0.00,
        'api_config': {'field_mapping': LINKEDIN_FIELD_MAPPING.dict()},
        'field_mapping': LINKEDIN_FIELD_MAPPING.dict(),
    }

    existing = await source_repo.get_source_by_name('linkedin')
    if existing:
        await source_repo.update(existing.id, {
            'base_url': source_data['base_url'],
            'api_config': source_data['api_config'],
            'field_mapping': source_data['field_mapping'],
        })
        return existing.id

    created = await source_repo.create(source_data)
    logger.info(f"Created LinkedIn source with ID: {created.id}")
    return created.id


async def validate_linkedin_config() -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    connection_test = await test_linkedin_connection()
    if not connection_test:
        errors.append("Could not reach the LinkedIn guest search endpoint")

    return ValidationResult(
        is_valid=len(errors) == 0, errors=errors, warnings=warnings, connection_test=connection_test,
    )


def build_source_config(source_id: int) -> SourceConfig:
    return SourceConfig(
        source_id=source_id,
        name='linkedin',
        source_type='scraping',
        base_url=LINKEDIN_SEARCH_URL,
        is_active=True,
        field_mapping=LINKEDIN_FIELD_MAPPING,
        extraction_rules=ExtractionRules(),
        batch_size=100,
    )
