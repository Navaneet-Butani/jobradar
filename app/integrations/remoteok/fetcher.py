"""RemoteOK fetcher service - main orchestration for job fetching and processing."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, NamedTuple
from dataclasses import dataclass, asdict

from .client import RemoteOKClient, RemoteOKAPIError, RemoteOKConnectionError, RemoteOKRateLimitError
from .parser import RemoteOKParser, parse_remoteok_jobs, ParsingStats
from .filter import RemoteOKFilter, FilterStats, FilterResult

from ...models.job import StandardJob
from ...models.base import ProcessingStats
from ...services.job_processor import JobProcessor
from ...services.location_parser import LocationParser
from ...services.salary_parser import SalaryParser
from ...services import create_job_processor, create_deduplication_service
from ...services.company_service import CompanyService
from ...services.skill_extractor import SkillExtractor
from ...services.validation_service import ValidationService
from ...repositories.job_repository import JobRepository
from ...repositories.company_repository import CompanyRepository
from ...core.exceptions import ProcessingError, ValidationError
from ...config.settings import settings

logger = logging.getLogger(__name__)


class FetchStats(NamedTuple):
    """Statistics for a RemoteOK fetch operation."""
    total_jobs_found: int
    it_jobs_filtered: int
    jobs_parsed: int
    jobs_processed: int
    jobs_added: int
    duplicates_found: int
    fetch_duration_seconds: float
    api_response_time_ms: float
    filter_inclusion_rate: float
    parsing_success_rate: float
    processing_success_rate: float
    api_calls_made: int
    errors_encountered: int
    cached_response: bool


@dataclass
class FetchResult:
    """Result from RemoteOK fetch operation."""
    success: bool
    stats: FetchStats
    error_message: Optional[str] = None
    jobs_added: List[Dict[str, Any]] = None
    excluded_jobs: List[Dict[str, Any]] = None
    processing_errors: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for logging."""
        return {
            'success': self.success,
            'stats': asdict(self.stats),
            'error_message': self.error_message,
            'jobs_added_count': len(self.jobs_added or []),
            'excluded_jobs_count': len(self.excluded_jobs or []),
            'processing_errors_count': len(self.processing_errors or [])
        }


@dataclass
class _BatchProcessingSummary:
    """Summary of a RemoteOK batch processing run (jobs already parsed to StandardJob)."""
    jobs_processed: int = 0
    jobs_added: int = 0
    duplicates_found: int = 0
    jobs_added_details: List[Dict[str, Any]] = None
    errors: List[str] = None
    success_rate: float = 0.0

    def __post_init__(self):
        if self.jobs_added_details is None:
            self.jobs_added_details = []
        if self.errors is None:
            self.errors = []


class RemoteOKFetcher:
    """Main fetcher service for RemoteOK job integration."""

    def __init__(self,
                 client: Optional[RemoteOKClient] = None,
                 job_processor: Optional[JobProcessor] = None,
                 location_parser: Optional[LocationParser] = None,
                 salary_parser: Optional[SalaryParser] = None,
                 filter_config: Optional[Dict[str, Any]] = None):
        """
        Initialize RemoteOK fetcher.

        Args:
            client: RemoteOK HTTP client
            job_processor: Job processing service
            location_parser: Location parsing service
            salary_parser: Salary parsing service
            filter_config: IT job filter configuration
        """
        self.client = client or RemoteOKClient()
        self.job_processor = job_processor or self._build_default_job_processor()
        self.location_parser = location_parser
        self.salary_parser = salary_parser
        self.filter = RemoteOKFilter(filter_config)
        self.source_id = None  # Will be set from database during initialization

        # Processing configuration
        self.batch_size = 100  # Process jobs in batches
        self.max_jobs_per_run = 1000  # Limit to prevent overwhelming
        self.enable_processing = True

    @staticmethod
    def _build_default_job_processor() -> JobProcessor:
        """Wire up a JobProcessor with its default dependencies."""
        job_repository = JobRepository()
        company_repository = CompanyRepository()
        company_service = CompanyService()
        deduplication_service = create_deduplication_service(job_repository, company_service)
        return create_job_processor(
            job_repository=job_repository,
            company_repository=company_repository,
            company_service=company_service,
            location_parser=LocationParser(),
            salary_parser=SalaryParser(),
            skill_extractor=SkillExtractor(),
            deduplication_service=deduplication_service,
            validation_service=ValidationService()
        )

    async def fetch_jobs(self) -> FetchResult:
        """
        Main method to fetch and process RemoteOK jobs.

        Returns:
            FetchResult with statistics and outcomes
        """
        start_time = datetime.now()
        api_calls_made = 0
        errors = []

        try:
            logger.info("Starting RemoteOK job fetch operation")

            # Step 1: Fetch all jobs from RemoteOK API
            async with self.client:
                try:
                    response = await self.client.fetch_all_jobs()
                    api_calls_made = 1

                    logger.info(f"Fetched {response.job_count} total jobs from RemoteOK "
                              f"in {response.response_time_ms:.2f}ms (cached: {response.cached})")

                except RemoteOKAPIError as e:
                    error_msg = f"RemoteOK API error: {e.message}"
                    logger.error(error_msg)
                    return self._create_error_result(error_msg, start_time, api_calls_made, [str(e)])

                except Exception as e:
                    error_msg = f"Unexpected error fetching from RemoteOK: {e}"
                    logger.error(error_msg)
                    return self._create_error_result(error_msg, start_time, api_calls_made, [str(e)])

            all_jobs = response.get_jobs()
            if not all_jobs:
                logger.warning("No jobs returned from RemoteOK API")
                return self._create_empty_result(start_time, response.response_time_ms, api_calls_made, response.cached)

            # Limit jobs to prevent excessive processing
            if len(all_jobs) > self.max_jobs_per_run:
                logger.info(f"Limiting to first {self.max_jobs_per_run} jobs out of {len(all_jobs)}")
                all_jobs = all_jobs[:self.max_jobs_per_run]

            # Step 2: Filter for IT-related jobs
            logger.info(f"Filtering {len(all_jobs)} jobs for IT positions")
            filter_result = self.filter.filter_jobs(all_jobs)

            it_jobs = [item['job'] for item in filter_result['included_jobs']]
            filter_stats = filter_result['stats']

            logger.info(f"Filtered to {len(it_jobs)} IT jobs "
                       f"({filter_stats.get_inclusion_rate():.1f}% inclusion rate)")

            if not it_jobs:
                logger.warning("No IT jobs found after filtering")
                return self._create_filtered_result(
                    all_jobs, filter_result, start_time, response.response_time_ms,
                    api_calls_made, response.cached
                )

            # Step 3: Parse jobs to StandardJob format
            logger.info(f"Parsing {len(it_jobs)} IT jobs to StandardJob format")
            try:
                parsed_jobs, parsing_stats = await parse_remoteok_jobs(
                    it_jobs, self.location_parser, self.salary_parser
                )

                logger.info(f"Parsed {parsing_stats.successfully_parsed}/{parsing_stats.total_jobs} "
                           f"jobs ({parsing_stats.success_rate:.1f}% success rate)")

                # Stamp the DB source_id — only the fetcher knows it, the parser doesn't.
                for parsed_job in parsed_jobs:
                    parsed_job.source_id = self.source_id or 1

            except Exception as e:
                error_msg = f"Error parsing RemoteOK jobs: {e}"
                logger.error(error_msg)
                errors.append(str(e))
                return self._create_error_result(error_msg, start_time, api_calls_made, errors)

            if not parsed_jobs:
                logger.warning("No jobs successfully parsed")
                return self._create_parsed_result(
                    all_jobs, filter_result, parsing_stats, start_time,
                    response.response_time_ms, api_calls_made, response.cached, errors
                )

            # Step 4: Process jobs through pipeline (if enabled)
            processing_result = None
            if self.enable_processing:
                logger.info(f"Processing {len(parsed_jobs)} parsed jobs through pipeline")
                try:
                    processing_result = await self._process_jobs_batch(parsed_jobs)

                    logger.info(f"Processing completed: {processing_result.jobs_added} added, "
                               f"{processing_result.duplicates_found} duplicates")

                except Exception as e:
                    error_msg = f"Error processing jobs: {e}"
                    logger.error(error_msg)
                    errors.append(str(e))
                    # Continue even if processing fails, return partial results

            # Create success result
            fetch_duration = (datetime.now() - start_time).total_seconds()

            stats = FetchStats(
                total_jobs_found=len(all_jobs),
                it_jobs_filtered=len(it_jobs),
                jobs_parsed=parsing_stats.successfully_parsed,
                jobs_processed=processing_result.jobs_processed if processing_result else 0,
                jobs_added=processing_result.jobs_added if processing_result else 0,
                duplicates_found=processing_result.duplicates_found if processing_result else 0,
                fetch_duration_seconds=fetch_duration,
                api_response_time_ms=response.response_time_ms,
                filter_inclusion_rate=filter_stats.get_inclusion_rate(),
                parsing_success_rate=parsing_stats.success_rate,
                processing_success_rate=processing_result.success_rate if processing_result else 0.0,
                api_calls_made=api_calls_made,
                errors_encountered=len(errors),
                cached_response=response.cached
            )

            logger.info(f"RemoteOK fetch completed successfully in {fetch_duration:.2f}s: "
                       f"{stats.jobs_added} jobs added, {stats.duplicates_found} duplicates")

            return FetchResult(
                success=True,
                stats=stats,
                jobs_added=processing_result.jobs_added_details if processing_result else [],
                excluded_jobs=filter_result['excluded_jobs'],
                processing_errors=errors
            )

        except Exception as e:
            error_msg = f"Unexpected error in RemoteOK fetch: {e}"
            logger.error(error_msg, exc_info=True)
            return self._create_error_result(error_msg, start_time, api_calls_made, [str(e)])

    async def _process_jobs_batch(self, jobs: List[StandardJob]) -> _BatchProcessingSummary:
        """Process already-parsed StandardJob objects through JobProcessor, in batches."""
        total_processed = 0
        total_added = 0
        total_duplicates = 0
        processing_errors = []

        # Process in batches
        for i in range(0, len(jobs), self.batch_size):
            batch = jobs[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (len(jobs) + self.batch_size - 1) // self.batch_size

            logger.debug(f"Processing batch {batch_num}/{total_batches} ({len(batch)} jobs)")

            try:
                batch_result = await self.job_processor.process_standard_job_batch(batch)

                total_processed += batch_result.successful_jobs
                total_added += batch_result.new_jobs_added
                total_duplicates += batch_result.duplicate_jobs

                if batch_result.errors:
                    processing_errors.extend(batch_result.errors)

            except Exception as e:
                logger.error(f"Error processing batch {batch_num}: {e}")
                processing_errors.append(f"Batch {batch_num} error: {e}")

        # Combine all results
        success_rate = (total_processed / len(jobs) * 100) if jobs else 0.0

        return _BatchProcessingSummary(
            jobs_processed=total_processed,
            jobs_added=total_added,
            duplicates_found=total_duplicates,
            jobs_added_details=[],  # Could collect details from all batches
            errors=processing_errors,
            success_rate=success_rate
        )

    def _create_error_result(self,
                           error_message: str,
                           start_time: datetime,
                           api_calls: int,
                           errors: List[str]) -> FetchResult:
        """Create error result."""
        duration = (datetime.now() - start_time).total_seconds()

        stats = FetchStats(
            total_jobs_found=0,
            it_jobs_filtered=0,
            jobs_parsed=0,
            jobs_processed=0,
            jobs_added=0,
            duplicates_found=0,
            fetch_duration_seconds=duration,
            api_response_time_ms=0.0,
            filter_inclusion_rate=0.0,
            parsing_success_rate=0.0,
            processing_success_rate=0.0,
            api_calls_made=api_calls,
            errors_encountered=len(errors),
            cached_response=False
        )

        return FetchResult(
            success=False,
            stats=stats,
            error_message=error_message,
            processing_errors=errors
        )

    def _create_empty_result(self,
                           start_time: datetime,
                           response_time_ms: float,
                           api_calls: int,
                           cached: bool) -> FetchResult:
        """Create result for empty response."""
        duration = (datetime.now() - start_time).total_seconds()

        stats = FetchStats(
            total_jobs_found=0,
            it_jobs_filtered=0,
            jobs_parsed=0,
            jobs_processed=0,
            jobs_added=0,
            duplicates_found=0,
            fetch_duration_seconds=duration,
            api_response_time_ms=response_time_ms,
            filter_inclusion_rate=0.0,
            parsing_success_rate=0.0,
            processing_success_rate=0.0,
            api_calls_made=api_calls,
            errors_encountered=0,
            cached_response=cached
        )

        return FetchResult(success=True, stats=stats, jobs_added=[], excluded_jobs=[])

    def _create_filtered_result(self,
                              all_jobs: List[Dict[str, Any]],
                              filter_result: Dict[str, Any],
                              start_time: datetime,
                              response_time_ms: float,
                              api_calls: int,
                              cached: bool) -> FetchResult:
        """Create result when no IT jobs found after filtering."""
        duration = (datetime.now() - start_time).total_seconds()
        filter_stats = filter_result['stats']

        stats = FetchStats(
            total_jobs_found=len(all_jobs),
            it_jobs_filtered=0,
            jobs_parsed=0,
            jobs_processed=0,
            jobs_added=0,
            duplicates_found=0,
            fetch_duration_seconds=duration,
            api_response_time_ms=response_time_ms,
            filter_inclusion_rate=filter_stats.get_inclusion_rate(),
            parsing_success_rate=0.0,
            processing_success_rate=0.0,
            api_calls_made=api_calls,
            errors_encountered=0,
            cached_response=cached
        )

        return FetchResult(
            success=True,
            stats=stats,
            jobs_added=[],
            excluded_jobs=filter_result['excluded_jobs']
        )

    def _create_parsed_result(self,
                            all_jobs: List[Dict[str, Any]],
                            filter_result: Dict[str, Any],
                            parsing_stats: ParsingStats,
                            start_time: datetime,
                            response_time_ms: float,
                            api_calls: int,
                            cached: bool,
                            errors: List[str]) -> FetchResult:
        """Create result when parsing fails."""
        duration = (datetime.now() - start_time).total_seconds()
        filter_stats = filter_result['stats']

        stats = FetchStats(
            total_jobs_found=len(all_jobs),
            it_jobs_filtered=filter_stats.included_jobs,
            jobs_parsed=parsing_stats.successfully_parsed,
            jobs_processed=0,
            jobs_added=0,
            duplicates_found=0,
            fetch_duration_seconds=duration,
            api_response_time_ms=response_time_ms,
            filter_inclusion_rate=filter_stats.get_inclusion_rate(),
            parsing_success_rate=parsing_stats.success_rate,
            processing_success_rate=0.0,
            api_calls_made=api_calls,
            errors_encountered=len(errors),
            cached_response=cached
        )

        return FetchResult(
            success=True,
            stats=stats,
            jobs_added=[],
            excluded_jobs=filter_result['excluded_jobs'],
            processing_errors=errors
        )

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on RemoteOK integration."""
        health_status = {
            'remoteok_api': False,
            'filter_configured': False,
            'parser_ready': False,
            'processor_ready': False,
            'errors': []
        }

        # Check API connectivity
        try:
            async with self.client:
                health_status['remoteok_api'] = await self.client.health_check()
        except Exception as e:
            health_status['errors'].append(f"API check failed: {e}")

        # Check filter configuration
        try:
            filter_stats = self.filter.get_filter_stats()
            health_status['filter_configured'] = (
                filter_stats['include_tags_count'] > 0 and
                filter_stats['exclude_tags_count'] > 0
            )
        except Exception as e:
            health_status['errors'].append(f"Filter check failed: {e}")

        # Check parser readiness
        try:
            # Simple parser test with minimal data
            parser = RemoteOKParser(self.location_parser, self.salary_parser)
            test_job = {
                'id': 'test',
                'position': 'Test Developer',
                'company': 'Test Company',
                'description': 'Test job description',
                'tags': ['python'],
                'date': '2024-01-01'
            }
            await parser.parse_job(test_job)
            health_status['parser_ready'] = True
        except Exception as e:
            health_status['errors'].append(f"Parser check failed: {e}")

        # Check processor readiness
        try:
            health_status['processor_ready'] = self.job_processor is not None
        except Exception as e:
            health_status['errors'].append(f"Processor check failed: {e}")

        # Overall health
        health_status['overall_healthy'] = (
            health_status['remoteok_api'] and
            health_status['filter_configured'] and
            health_status['parser_ready'] and
            health_status['processor_ready'] and
            len(health_status['errors']) == 0
        )

        return health_status

    def get_configuration(self) -> Dict[str, Any]:
        """Get fetcher configuration for monitoring."""
        return {
            'batch_size': self.batch_size,
            'max_jobs_per_run': self.max_jobs_per_run,
            'enable_processing': self.enable_processing,
            'source_id': self.source_id,
            'client_config': {
                'base_url': self.client.base_url,
                'cache_ttl': self.client.cache_ttl,
                'timeout': self.client.timeout
            },
            'filter_config': self.filter.get_filter_stats()
        }