"""RemoteOK API configuration management."""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, NamedTuple
from dataclasses import dataclass

from ...models.source import SourceConfig, FieldMapping, ExtractionRules
from ...repositories.source_repository import SourceRepository
from ...core.exceptions import ValidationError, ProcessingError
from ...config.settings import settings
from .client import RemoteOKClient, test_remoteok_connection

logger = logging.getLogger(__name__)


class ValidationResult(NamedTuple):
    """Result of configuration validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    connection_test: bool


@dataclass
class RemoteOKConfig:
    """RemoteOK-specific configuration data."""
    base_url: str
    rate_limit: Dict[str, int]
    cache_ttl: int
    attribution: Dict[str, str]
    filter_config: Dict[str, Any]
    field_mapping: Dict[str, str]
    extraction_rules: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'base_url': self.base_url,
            'rate_limit': self.rate_limit,
            'cache_ttl': self.cache_ttl,
            'attribution': self.attribution,
            'filter_config': self.filter_config,
            'field_mapping': self.field_mapping,
            'extraction_rules': self.extraction_rules,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RemoteOKConfig':
        """Create from dictionary."""
        return cls(**data)


class RemoteOKConfigManager:
    """Manager for RemoteOK API configuration."""

    def __init__(self):
        self.source_repository = SourceRepository()

    async def get_default_config(self) -> RemoteOKConfig:
        """Get default RemoteOK configuration."""
        return RemoteOKConfig(
            base_url="https://remoteok.io/api",
            rate_limit={
                "calls_per_second": 1,
                "burst_size": 1
            },
            cache_ttl=3600,  # 1 hour cache for API responses
            attribution={
                "source_name": "RemoteOK",
                "source_text": "Jobs sourced from RemoteOK.io",
                "source_url": "https://remoteok.io",
                "backlink_required": True
            },
            filter_config={
                "include_tags": [
                    # Backend
                    "dev", "developer", "engineer", "engineering",
                    "python", "javascript", "java", "golang", "go", "rust",
                    "node", "nodejs", "django", "flask", "rails", "laravel",
                    "php", "ruby", "csharp", "dotnet", ".net", "scala",

                    # Frontend
                    "frontend", "front-end", "react", "angular", "vue", "vuejs",
                    "html", "css", "sass", "scss", "typescript", "ts",
                    "jquery", "bootstrap", "tailwind", "next", "nuxt",

                    # Full-stack
                    "fullstack", "full-stack", "full stack",

                    # DevOps/Cloud
                    "devops", "cloud", "aws", "azure", "gcp", "kubernetes",
                    "docker", "terraform", "ansible", "jenkins", "cicd",
                    "infrastructure", "sre", "platform",

                    # Data
                    "data", "ml", "ai", "machine learning", "data science",
                    "data engineer", "analytics", "bigdata", "spark", "hadoop",
                    "sql", "nosql", "mongodb", "postgresql", "mysql",

                    # Mobile
                    "ios", "android", "mobile", "react native", "flutter",
                    "swift", "kotlin", "xamarin",

                    # Other
                    "qa", "testing", "automation", "security", "blockchain",
                    "embedded", "iot", "game", "gaming", "unity", "unreal"
                ],
                "exclude_tags": [
                    "sales", "marketing", "design", "hr", "customer support",
                    "writing", "content", "copywriting", "seo", "social media",
                    "accounting", "finance", "legal", "operations", "admin",
                    "management", "project manager", "product manager",
                    "business development", "business analyst"
                ],
                "max_age_days": 30,
                "min_quality_score": 0.5,
                "require_salary": False
            },
            field_mapping={
                "title": "position",
                "company": "company",
                "description": "description",
                "tags": "tags",
                "posted_date": "date",
                "apply_url": "apply_url",
                "source_url": "url",
                "salary_min": "salary_min",
                "salary_max": "salary_max",
                "location": "location",
                "external_id": "id"
            },
            extraction_rules={
                "remote_keywords": [
                    "remote", "work from home", "distributed", "anywhere",
                    "nomad", "wfh", "telecommute", "virtual"
                ],
                "experience_patterns": [
                    r"\b([0-9]+)\+?\s*years?\s*(?:of\s*)?(?:experience|exp)\b",
                    r"\bsenior\b", r"\bjunior\b", r"\blead\b", r"\bprincipal\b",
                    r"\bentry\s*level\b", r"\bmid\s*level\b", r"\bstaff\b"
                ],
                "salary_patterns": [
                    r"\$([0-9,]+)(?:\s*-\s*\$?([0-9,]+))?(?:\s*(?:per\s*year|annually|yearly|/year|/yr))?",
                    r"([0-9,]+)k?(?:\s*-\s*([0-9,]+)k?)?\s*(?:usd|dollars?)",
                    r"salary:?\s*\$?([0-9,]+)(?:\s*-\s*\$?([0-9,]+))?"
                ],
                "html_clean": {
                    "strip_tags": True,
                    "preserve_links": False,
                    "max_length": 5000
                }
            }
        )

    async def create_source_record(self) -> int:
        """Create RemoteOK source record in database."""
        try:
            config = await self.get_default_config()

            # Check if RemoteOK source already exists
            existing = await self.source_repository.get_source_by_name("remoteok")
            if existing:
                logger.info("RemoteOK source already exists, updating configuration")
                # Update existing record
                await self.source_repository.update(
                    existing.id,
                    {'api_config': config.to_dict(), 'field_mapping': config.field_mapping}
                )
                return existing.id

            # Create new source record
            from ...models import JobSourceDB
            source_data = {
                'name': 'remoteok',
                'type': 'api',
                'base_url': config.base_url,
                'is_active': True,
                'hourly_quota': 60,  # 1 per second * 60 seconds
                'daily_quota': 86400,  # 1 per second * 86400 seconds
                'monthly_quota': 2592000,  # 30 days worth
                'cost_per_call': 0.0000,  # Free API
                'monthly_budget': 0.00,  # Free
                'api_config': config.to_dict(),
                'field_mapping': config.field_mapping
            }

            created = await self.source_repository.create(source_data)
            logger.info(f"Created RemoteOK source with ID: {created.id}")
            return created.id

        except Exception as e:
            logger.error(f"Error creating RemoteOK source record: {e}")
            raise ProcessingError(f"Failed to create RemoteOK source: {e}")

    async def validate_config(self) -> ValidationResult:
        """Validate RemoteOK configuration."""
        errors = []
        warnings = []
        connection_test = False

        try:
            # Get configuration
            config = await self.get_default_config()

            # Validate basic configuration
            if not config.base_url:
                errors.append("Base URL is required")
            elif not config.base_url.startswith('https://'):
                warnings.append("Base URL should use HTTPS")

            if not config.attribution.get('source_name'):
                errors.append("Attribution source name is required")

            if not config.field_mapping:
                errors.append("Field mapping is required")

            if not config.filter_config.get('include_tags'):
                warnings.append("No include tags defined for IT job filtering")

            # Test connection
            try:
                connection_test = await test_remoteok_connection()
                if not connection_test:
                    errors.append("Failed to connect to RemoteOK API")
            except Exception as e:
                errors.append(f"Connection test failed: {e}")

        except Exception as e:
            errors.append(f"Configuration validation error: {e}")

        is_valid = len(errors) == 0
        return ValidationResult(is_valid, errors, warnings, connection_test)


async def setup_remoteok_source() -> bool:
    """Set up RemoteOK source configuration."""
    try:
        manager = RemoteOKConfigManager()
        source_id = await manager.create_source_record()

        # Validate configuration
        validation = await manager.validate_config()
        if not validation.is_valid:
            logger.error(f"RemoteOK configuration validation failed: {validation.errors}")
            return False

        if validation.warnings:
            logger.warning(f"RemoteOK configuration warnings: {validation.warnings}")

        logger.info(f"RemoteOK source setup completed successfully (ID: {source_id})")
        return True

    except Exception as e:
        logger.error(f"Failed to setup RemoteOK source: {e}")
        return False


async def validate_remoteok_config() -> ValidationResult:
    """Validate RemoteOK configuration."""
    manager = RemoteOKConfigManager()
    return await manager.validate_config()