"""Remotive source configuration.

Open JSON API, no auth (docs/sources.md). Heavily US/EU-weighted —
kept off by default (REMOTIVE_ENABLED).
"""

import logging
from typing import NamedTuple, List

from ...models.source import SourceConfig, FieldMapping, ExtractionRules
from ...repositories.source_repository import SourceRepository
from ...config.settings import settings
from .client import test_remotive_connection

logger = logging.getLogger(__name__)

REMOTIVE_FIELD_MAPPING = FieldMapping(
    title=["title"],
    company=["company_name"],
    location=["candidate_required_location"],
    description=["description"],
    apply_url=["url"],
    skills_required=["tags"],
    posted_date=["publication_date"],   # already ISO8601
    salary=["salary"],                  # free text, e.g. "$170k - $200k"
)


class ValidationResult(NamedTuple):
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    connection_test: bool


async def setup_remotive_source() -> int:
    """Register (or update) the Remotive source row. Returns the source_id."""
    source_repo = SourceRepository()

    source_data = {
        'name': 'remotive',
        'type': 'api',
        'base_url': settings.remotive_base_url,
        'is_active': True,
        'hourly_quota': 60,
        'daily_quota': 500,
        'monthly_quota': 15000,
        'cost_per_call': 0.0000,
        'monthly_budget': 0.00,
        'api_config': {'field_mapping': REMOTIVE_FIELD_MAPPING.dict()},
        'field_mapping': REMOTIVE_FIELD_MAPPING.dict(),
    }

    existing = await source_repo.get_source_by_name('remotive')
    if existing:
        await source_repo.update(existing.id, {
            'base_url': source_data['base_url'],
            'api_config': source_data['api_config'],
            'field_mapping': source_data['field_mapping'],
        })
        return existing.id

    created = await source_repo.create(source_data)
    logger.info(f"Created Remotive source with ID: {created.id}")
    return created.id


async def validate_remotive_config() -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    connection_test = await test_remotive_connection()
    if not connection_test:
        errors.append("Could not connect to Remotive API")

    return ValidationResult(
        is_valid=len(errors) == 0, errors=errors, warnings=warnings, connection_test=connection_test,
    )


def build_source_config(source_id: int) -> SourceConfig:
    return SourceConfig(
        source_id=source_id,
        name='remotive',
        source_type='api',
        base_url=settings.remotive_base_url,
        is_active=True,
        field_mapping=REMOTIVE_FIELD_MAPPING,
        extraction_rules=ExtractionRules(),
        batch_size=100,
    )
