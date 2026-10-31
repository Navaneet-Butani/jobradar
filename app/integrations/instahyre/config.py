"""Instahyre source configuration."""

import logging
from typing import NamedTuple, List

from ...models.source import SourceConfig, FieldMapping, ExtractionRules
from ...repositories.source_repository import SourceRepository
from ...config.settings import settings
from .client import test_instahyre_connection

logger = logging.getLogger(__name__)

# Instahyre's list payload is already clean structured JSON — no salary or
# experience range at this level (per docs/sources.md).
INSTAHYRE_FIELD_MAPPING = FieldMapping(
    title=["title", "candidate_title"],
    company=["employer.company_name"],   # nested — dot notation
    location=["locations"],
    apply_url=["public_url"],
    skills_required=["keywords"],        # already a clean array
)


class ValidationResult(NamedTuple):
    """Result of configuration validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    connection_test: bool


async def setup_instahyre_source() -> int:
    """Register (or update) the Instahyre source row. Returns the source_id."""
    source_repo = SourceRepository()

    source_data = {
        'name': 'instahyre',
        'type': 'api',
        'base_url': settings.instahyre_base_url,
        'is_active': True,
        'hourly_quota': 3600,   # 1/sec
        'daily_quota': 50000,
        'monthly_quota': 1500000,
        'cost_per_call': 0.0000,
        'monthly_budget': 0.00,
        'api_config': {'field_mapping': INSTAHYRE_FIELD_MAPPING.dict()},
        'field_mapping': INSTAHYRE_FIELD_MAPPING.dict(),
    }

    existing = await source_repo.get_source_by_name('instahyre')
    if existing:
        await source_repo.update(existing.id, {
            'base_url': source_data['base_url'],
            'api_config': source_data['api_config'],
            'field_mapping': source_data['field_mapping'],
        })
        logger.info(f"Instahyre source already exists (ID: {existing.id}), updated configuration")
        return existing.id

    created = await source_repo.create(source_data)
    logger.info(f"Created Instahyre source with ID: {created.id}")
    return created.id


async def validate_instahyre_config() -> ValidationResult:
    """Validate Instahyre configuration and connectivity."""
    errors: List[str] = []
    warnings: List[str] = []

    if not settings.instahyre_base_url:
        errors.append("instahyre_base_url is not configured")

    connection_test = await test_instahyre_connection()
    if not connection_test:
        errors.append("Could not connect to Instahyre API")

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        connection_test=connection_test,
    )


def build_source_config(source_id: int) -> SourceConfig:
    """Build the SourceConfig used by the pipeline's FieldExtractor."""
    return SourceConfig(
        source_id=source_id,
        name='instahyre',
        source_type='api',
        base_url=settings.instahyre_base_url,
        is_active=True,
        field_mapping=INSTAHYRE_FIELD_MAPPING,
        extraction_rules=ExtractionRules(),
        batch_size=100,
    )
