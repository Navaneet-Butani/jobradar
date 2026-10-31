"""Arbeitnow source configuration.

Open JSON API, no auth (docs/sources.md). Heavily EU-weighted —
kept off by default (ARBEITNOW_ENABLED), the matching engine's
remote_scope classifier is what keeps US/EU-only postings out of the feed.
"""

import logging
from typing import NamedTuple, List

from ...models.source import SourceConfig, FieldMapping, ExtractionRules
from ...repositories.source_repository import SourceRepository
from ...config.settings import settings
from .client import test_arbeitnow_connection

logger = logging.getLogger(__name__)

ARBEITNOW_FIELD_MAPPING = FieldMapping(
    title=["title"],
    company=["company_name"],
    location=["location"],          # normalized in fetcher.py to append "Remote" when applicable
    description=["description"],
    apply_url=["url"],
    skills_required=["tags"],
    posted_date=["created_at"],     # normalized in fetcher.py from unix epoch to ISO8601
)


class ValidationResult(NamedTuple):
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    connection_test: bool


async def setup_arbeitnow_source() -> int:
    """Register (or update) the Arbeitnow source row. Returns the source_id."""
    source_repo = SourceRepository()

    source_data = {
        'name': 'arbeitnow',
        'type': 'api',
        'base_url': settings.arbeitnow_base_url,
        'is_active': True,
        'hourly_quota': 60,
        'daily_quota': 500,
        'monthly_quota': 15000,
        'cost_per_call': 0.0000,
        'monthly_budget': 0.00,
        'api_config': {'field_mapping': ARBEITNOW_FIELD_MAPPING.dict()},
        'field_mapping': ARBEITNOW_FIELD_MAPPING.dict(),
    }

    existing = await source_repo.get_source_by_name('arbeitnow')
    if existing:
        await source_repo.update(existing.id, {
            'base_url': source_data['base_url'],
            'api_config': source_data['api_config'],
            'field_mapping': source_data['field_mapping'],
        })
        return existing.id

    created = await source_repo.create(source_data)
    logger.info(f"Created Arbeitnow source with ID: {created.id}")
    return created.id


async def validate_arbeitnow_config() -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    connection_test = await test_arbeitnow_connection()
    if not connection_test:
        errors.append("Could not connect to Arbeitnow API")

    return ValidationResult(
        is_valid=len(errors) == 0, errors=errors, warnings=warnings, connection_test=connection_test,
    )


def build_source_config(source_id: int) -> SourceConfig:
    return SourceConfig(
        source_id=source_id,
        name='arbeitnow',
        source_type='api',
        base_url=settings.arbeitnow_base_url,
        is_active=True,
        field_mapping=ARBEITNOW_FIELD_MAPPING,
        extraction_rules=ExtractionRules(),
        batch_size=100,
    )
