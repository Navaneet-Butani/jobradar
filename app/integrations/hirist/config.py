"""Hirist source configuration.

India tech-only board. docs/sources.md documented this as an
HTML/__NEXT_DATA__ scrape, but that blob ships empty (SSR placeholder —
the real data loads client-side after hydration). Found the actual
JSON API instead by inspecting live network traffic: gladiator.hirist.tech.
Undocumented, so treat it the same as Instahyre's undocumented API —
liable to change without notice, re-verify if it starts 404ing.

Like Instahyre, the `query` text's location portion doesn't actually
filter by city (verified live — "Python Developer In Ahmedabad" and
"...In Bangalore" return the same total and same top result). Only the
keyword portion narrows results, so this fetches by keyword only and
filters India/location eligibility locally, same as every other source
here without working server-side location filters.
"""

import logging
from typing import NamedTuple, List

from ...models.source import SourceConfig, FieldMapping, ExtractionRules
from ...repositories.source_repository import SourceRepository
from .client import test_hirist_connection, HIRIST_SEARCH_URL

logger = logging.getLogger(__name__)

HIRIST_FIELD_MAPPING = FieldMapping(
    title=["title"],
    company=["companyData.companyName"],
    location=["location"],              # normalized in fetcher.py from locations[] + workFromHome
    apply_url=["jobDetailUrl"],
    skills_required=["skills"],         # normalized in fetcher.py from tags[].name
    posted_date=["createdTime"],        # normalized in fetcher.py from epoch-ms to ISO8601
    salary_min=["minSal"],
    salary_max=["maxSal"],
    min_exp_years=["min"],              # years of experience, stated by the board
    max_exp_years=["max"],
)


class ValidationResult(NamedTuple):
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    connection_test: bool


async def setup_hirist_source() -> int:
    """Register (or update) the Hirist source row. Returns the source_id."""
    source_repo = SourceRepository()

    source_data = {
        'name': 'hirist',
        'type': 'api',
        'base_url': HIRIST_SEARCH_URL,
        'is_active': True,
        'hourly_quota': 120,
        'daily_quota': 1000,
        'monthly_quota': 30000,
        'cost_per_call': 0.0000,
        'monthly_budget': 0.00,
        'api_config': {'field_mapping': HIRIST_FIELD_MAPPING.dict()},
        'field_mapping': HIRIST_FIELD_MAPPING.dict(),
    }

    existing = await source_repo.get_source_by_name('hirist')
    if existing:
        await source_repo.update(existing.id, {
            'base_url': source_data['base_url'],
            'api_config': source_data['api_config'],
            'field_mapping': source_data['field_mapping'],
        })
        return existing.id

    created = await source_repo.create(source_data)
    logger.info(f"Created Hirist source with ID: {created.id}")
    return created.id


async def validate_hirist_config() -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    connection_test = await test_hirist_connection()
    if not connection_test:
        errors.append("Could not connect to Hirist API")

    return ValidationResult(
        is_valid=len(errors) == 0, errors=errors, warnings=warnings, connection_test=connection_test,
    )


def build_source_config(source_id: int) -> SourceConfig:
    return SourceConfig(
        source_id=source_id,
        name='hirist',
        source_type='api',
        base_url=HIRIST_SEARCH_URL,
        is_active=True,
        field_mapping=HIRIST_FIELD_MAPPING,
        extraction_rules=ExtractionRules(),
        batch_size=100,
    )
