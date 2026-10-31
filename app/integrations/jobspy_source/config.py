"""JobSpy (Indeed + LinkedIn) source configuration and search matrix."""

import logging
from typing import List

from ...models.source import SourceConfig, FieldMapping, ExtractionRules
from ...repositories.source_repository import SourceRepository

logger = logging.getLogger(__name__)

# JobSpy's DataFrame columns land directly in raw_data (via .to_dict()), so
# these map straight through — no injected fields needed, unlike ATS.
JOBSPY_FIELD_MAPPING = FieldMapping(
    title=["title"],
    company=["company"],
    location=["location"],
    apply_url=["job_url_direct", "job_url"],   # prefer the direct employer link when JobSpy found one
    description=["description"],
    salary_min=["min_amount"],
    salary_max=["max_amount"],
    salary_currency=["currency"],
    salary_period=["interval"],
    employment_type=["job_type"],
    posted_date=["date_posted"],
    skills_required=["skills"],
)

REMOTE_LOCATION = "India"


def linkedin_priority_order(cities: List[str], terms: List[str]) -> List[tuple]:
    """
    Primary cities x terms first, remote sweep after — the order LinkedIn's
    limited per-run budget should be spent in. Used with a rotating offset
    (see rate_limiter.next_rotation_offset) so coverage cycles through this
    list across runs instead of always landing on the same entry.
    """
    ordered = [(city, term) for city in cities for term in terms]
    ordered += [(None, term) for term in terms]
    return ordered


async def setup_jobspy_source() -> int:
    """Register (or update) the single shared 'jobspy' source row. Returns the source_id."""
    source_repo = SourceRepository()

    source_data = {
        'name': 'jobspy',
        'type': 'scraping',
        'base_url': 'https://in.indeed.com',
        'is_active': True,
        'hourly_quota': 200,
        'daily_quota': 2000,
        'monthly_quota': 60000,
        'cost_per_call': 0.0000,
        'monthly_budget': 0.00,
        'api_config': {'field_mapping': JOBSPY_FIELD_MAPPING.dict(), 'sites': ['indeed', 'linkedin']},
        'field_mapping': JOBSPY_FIELD_MAPPING.dict(),
    }

    existing = await source_repo.get_source_by_name('jobspy')
    if existing:
        await source_repo.update(existing.id, {
            'api_config': source_data['api_config'],
            'field_mapping': source_data['field_mapping'],
        })
        logger.info(f"JobSpy source already exists (ID: {existing.id}), updated configuration")
        return existing.id

    created = await source_repo.create(source_data)
    logger.info(f"Created JobSpy source with ID: {created.id}")
    return created.id


def build_source_config(source_id: int) -> SourceConfig:
    """Build the SourceConfig used by the pipeline's FieldExtractor."""
    return SourceConfig(
        source_id=source_id,
        name='jobspy',
        source_type='scraping',
        base_url='https://in.indeed.com',
        is_active=True,
        field_mapping=JOBSPY_FIELD_MAPPING,
        extraction_rules=ExtractionRules(),
        batch_size=100,
    )
