"""Himalayas source configuration.

Open JSON API, no auth (docs/sources.md). Huge corpus (~100k+
jobs, heavily global) with no server-side location filter — the fetcher
caps how many recent pages it pulls (see MAX_PAGES in fetcher.py) rather
than ingesting the full corpus. Kept off by default (HIMALAYAS_ENABLED).
"""

import logging
from typing import NamedTuple, List

from ...models.source import SourceConfig, FieldMapping, ExtractionRules
from ...repositories.source_repository import SourceRepository
from ...config.settings import settings
from .client import test_himalayas_connection

logger = logging.getLogger(__name__)

HIMALAYAS_FIELD_MAPPING = FieldMapping(
    title=["title"],
    company=["companyName"],
    location=["locationRestrictions"],   # normalized in fetcher.py: list -> comma string
    description=["description"],
    apply_url=["applicationLink"],
    skills_required=["categories"],
    posted_date=["pubDate"],             # normalized in fetcher.py from unix epoch to ISO8601
    salary_min=["minSalary"],
    salary_max=["maxSalary"],
    salary_currency=["currency"],
    salary_period=["salaryPeriod"],
)


class ValidationResult(NamedTuple):
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    connection_test: bool


async def setup_himalayas_source() -> int:
    """Register (or update) the Himalayas source row. Returns the source_id."""
    source_repo = SourceRepository()

    source_data = {
        'name': 'himalayas',
        'type': 'api',
        'base_url': settings.himalayas_base_url,
        'is_active': True,
        'hourly_quota': 60,
        'daily_quota': 500,
        'monthly_quota': 15000,
        'cost_per_call': 0.0000,
        'monthly_budget': 0.00,
        'api_config': {'field_mapping': HIMALAYAS_FIELD_MAPPING.dict()},
        'field_mapping': HIMALAYAS_FIELD_MAPPING.dict(),
    }

    existing = await source_repo.get_source_by_name('himalayas')
    if existing:
        await source_repo.update(existing.id, {
            'base_url': source_data['base_url'],
            'api_config': source_data['api_config'],
            'field_mapping': source_data['field_mapping'],
        })
        return existing.id

    created = await source_repo.create(source_data)
    logger.info(f"Created Himalayas source with ID: {created.id}")
    return created.id


async def validate_himalayas_config() -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    connection_test = await test_himalayas_connection()
    if not connection_test:
        errors.append("Could not connect to Himalayas API")

    return ValidationResult(
        is_valid=len(errors) == 0, errors=errors, warnings=warnings, connection_test=connection_test,
    )


def build_source_config(source_id: int) -> SourceConfig:
    return SourceConfig(
        source_id=source_id,
        name='himalayas',
        source_type='api',
        base_url=settings.himalayas_base_url,
        is_active=True,
        field_mapping=HIMALAYAS_FIELD_MAPPING,
        extraction_rules=ExtractionRules(),
        batch_size=100,
    )
