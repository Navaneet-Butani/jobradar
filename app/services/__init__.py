"""Job processing and search services module.

This module contains all the core services for processing job data and user-facing search:
- FieldExtractor: Extract fields from raw job data with configurable mappings
- LocationParser: Parse and normalize location information
- SalaryParser: Parse salary information with multi-currency support
- CompanyService: Company normalization and fuzzy matching
- DeduplicationService: Job deduplication using hash-based and fuzzy matching
- ValidationService: Data quality validation and spam detection
- JobProcessor: Main processing pipeline orchestrator
"""

from .field_extractor import FieldExtractor, FieldExtractionResult
from .location_parser import LocationParser, ParsedLocation
from .salary_parser import SalaryParser, ParsedSalary
from .company_service import CompanyService
from .deduplication_service import DeduplicationService, DuplicateMatch
from .validation_service import ValidationService, QualityMetrics
from .job_processor import JobProcessor, ProcessingResult, BatchProcessingResult

__all__ = [
    # Field extraction
    'FieldExtractor',
    'FieldExtractionResult',

    # Location processing
    'LocationParser',
    'ParsedLocation',

    # Salary processing
    'SalaryParser',
    'ParsedSalary',

    # Company processing
    'CompanyService',

    # Deduplication
    'DeduplicationService',
    'DuplicateMatch',

    # Validation and quality
    'ValidationService',
    'QualityMetrics',

    # Main processor
    'JobProcessor',
    'ProcessingResult',
    'BatchProcessingResult',
]


# Service factory functions for dependency injection
def create_job_processor(job_repository, company_repository, company_service,
                        location_parser, salary_parser, skill_extractor,
                        deduplication_service, validation_service) -> JobProcessor:
    """Create JobProcessor with all dependencies."""
    return JobProcessor(
        job_repository=job_repository,
        company_repository=company_repository,
        company_service=company_service,
        location_parser=location_parser,
        salary_parser=salary_parser,
        skill_extractor=skill_extractor,
        deduplication_service=deduplication_service,
        validation_service=validation_service
    )


def create_deduplication_service(job_repository, company_service) -> DeduplicationService:
    """Create DeduplicationService with dependencies."""
    return DeduplicationService(
        job_repository=job_repository,
        company_service=company_service
    )


def create_location_parser() -> LocationParser:
    """Create LocationParser instance."""
    return LocationParser()


def create_salary_parser() -> SalaryParser:
    """Create SalaryParser instance.""" 
    return SalaryParser()


def create_validation_service() -> ValidationService:
    """Create ValidationService instance."""
    return ValidationService()



# Version information
__version__ = "1.0.0"
__author__ = "Job Portal API Team"
