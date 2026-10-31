"""ATS source configuration.

Greenhouse, Lever, Ashby, SmartRecruiters and Recruitee all get normalized
to the same shape before reaching FieldMapping — each provider module injects _company_name,
_apply_url, _location, and (where available) _posted_date onto the raw
job dict, so one FieldMapping covers all three.
"""

import logging
from typing import List

from ...models.source import SourceConfig, FieldMapping, ExtractionRules
from ...repositories.source_repository import SourceRepository
from ...config.settings import settings

logger = logging.getLogger(__name__)

ATS_FIELD_MAPPING = FieldMapping(
    title=["title", "text"],                              # Greenhouse/Ashby use "title", Lever uses "text"
    company=["_company_name"],                             # injected — not present in any provider's payload
    location=["_location"],                                # injected — flattened from each provider's nested shape
    apply_url=["_apply_url"],                               # injected — constructed per-provider
    description=["content", "descriptionPlain", "description"],
    posted_date=["_posted_date"],                           # injected — normalized to a parseable string
)


async def setup_ats_source() -> int:
    """Register (or update) the single shared 'ats' source row. Returns the source_id."""
    source_repo = SourceRepository()

    source_data = {
        'name': 'ats',
        'type': 'api',
        'base_url': 'https://boards-api.greenhouse.io',  # representative; each company polls its own board
        'is_active': True,
        'hourly_quota': 7200,
        'daily_quota': 100000,
        'monthly_quota': 3000000,
        'cost_per_call': 0.0000,
        'monthly_budget': 0.00,
        'api_config': {'field_mapping': ATS_FIELD_MAPPING.dict(), 'providers': ['greenhouse', 'lever', 'ashby', 'smartrecruiters', 'recruitee']},
        'field_mapping': ATS_FIELD_MAPPING.dict(),
    }

    existing = await source_repo.get_source_by_name('ats')
    if existing:
        await source_repo.update(existing.id, {
            'api_config': source_data['api_config'],
            'field_mapping': source_data['field_mapping'],
        })
        logger.info(f"ATS source already exists (ID: {existing.id}), updated configuration")
        return existing.id

    created = await source_repo.create(source_data)
    logger.info(f"Created ATS source with ID: {created.id}")
    return created.id


def build_source_config(source_id: int) -> SourceConfig:
    """Build the SourceConfig used by the pipeline's FieldExtractor."""
    return SourceConfig(
        source_id=source_id,
        name='ats',
        source_type='api',
        base_url='https://boards-api.greenhouse.io',
        is_active=True,
        field_mapping=ATS_FIELD_MAPPING,
        extraction_rules=ExtractionRules(),
        batch_size=100,
    )
