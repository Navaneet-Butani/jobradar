"""Instahyre fetcher service — orchestrates paginated fetch and processing."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional

from .client import InstahyreClient, InstahyreRateLimitError
from .config import build_source_config
from ...models.source import RawJobData
from ...services.job_processor import JobProcessor, BatchProcessingResult
from ...repositories.job_repository import JobRepository
from ...repositories.company_repository import CompanyRepository
from ...services.company_service import CompanyService
from ...services.location_parser import LocationParser
from ...services.salary_parser import SalaryParser
from ...services.skill_extractor import SkillExtractor
from ...services.deduplication_service import DeduplicationService
from ...services.validation_service import ValidationService

logger = logging.getLogger(__name__)

PAGE_LIMIT = 35
MAX_PAGES = 500  # hard ceiling — ~13.9k jobs / 35 per page ≈ 398 pages
MAX_RATE_LIMIT_RETRIES = 5


@dataclass
class FetchResult:
    """Result of an Instahyre full-corpus sync."""
    success: bool
    pages_fetched: int = 0
    jobs_seen: int = 0
    jobs_processed: int = 0
    jobs_added: int = 0
    duplicates_found: int = 0
    errors: List[str] = field(default_factory=list)


class InstahyreFetcher:
    """Fetches the full Instahyre corpus and runs it through the ingest pipeline."""

    def __init__(self,
                 source_id: int,
                 client: Optional[InstahyreClient] = None,
                 job_processor: Optional[JobProcessor] = None):
        self.source_id = source_id
        self.client = client or InstahyreClient()
        self.job_processor = job_processor or self._build_default_job_processor()
        self.source_config = build_source_config(source_id)

    @staticmethod
    def _build_default_job_processor() -> JobProcessor:
        """Wire up a JobProcessor with its default dependencies."""
        job_repository = JobRepository()
        company_repository = CompanyRepository()
        company_service = CompanyService()
        deduplication_service = DeduplicationService(job_repository, company_service)
        return JobProcessor(
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
        """Fetch the full Instahyre corpus (paginated) and process every job."""
        result = FetchResult(success=False)

        async with self.client:
            offset = 0
            total_count: Optional[int] = None
            rate_limit_retries = 0

            while True:
                if offset // PAGE_LIMIT >= MAX_PAGES:
                    logger.warning(f"Hit MAX_PAGES={MAX_PAGES} safety ceiling, stopping")
                    break

                try:
                    page = await self.client.fetch_page(offset)
                    rate_limit_retries = 0
                except InstahyreRateLimitError as e:
                    rate_limit_retries += 1
                    if rate_limit_retries > MAX_RATE_LIMIT_RETRIES:
                        logger.error(f"Rate limit retries exhausted at offset {offset}")
                        result.errors.append(f"Rate limit retries exhausted at offset {offset}: {e}")
                        break
                    retry_after = e.response_data.get('retry_after')
                    wait_seconds = float(retry_after) if retry_after else min(60, 5 * (2 ** (rate_limit_retries - 1)))
                    logger.warning(
                        f"Instahyre rate limited at offset {offset}, waiting {wait_seconds:.0f}s "
                        f"(attempt {rate_limit_retries}/{MAX_RATE_LIMIT_RETRIES})"
                    )
                    await asyncio.sleep(wait_seconds)
                    continue
                except Exception as e:
                    logger.error(f"Error fetching Instahyre page at offset {offset}: {e}")
                    result.errors.append(f"Fetch error at offset {offset}: {e}")
                    break

                result.pages_fetched += 1
                total_count = page.total_count

                if not page.objects:
                    logger.info(f"No more objects at offset {offset}, stopping")
                    break

                raw_jobs = [
                    RawJobData(
                        source_id=self.source_id,
                        external_id=str(obj.get('id')),
                        raw_data=obj,
                        source_url=obj.get('public_url'),
                        fetched_at=datetime.utcnow(),
                    )
                    for obj in page.objects
                    if obj.get('id') is not None
                ]
                result.jobs_seen += len(raw_jobs)

                batch_result = await self.job_processor.process_job_batch(raw_jobs, self.source_config)
                result.jobs_processed += batch_result.successful_jobs
                result.jobs_added += batch_result.new_jobs_added
                result.duplicates_found += batch_result.duplicate_jobs
                if batch_result.errors:
                    result.errors.extend(batch_result.errors)

                logger.info(
                    f"Instahyre progress: offset={offset}/{total_count}, "
                    f"added={result.jobs_added}, duplicates={result.duplicates_found}"
                )

                offset += PAGE_LIMIT
                if total_count is not None and offset >= total_count:
                    break

        result.success = len(result.errors) == 0 or result.jobs_added > 0
        logger.info(
            f"Instahyre sync complete: {result.pages_fetched} pages, "
            f"{result.jobs_seen} seen, {result.jobs_added} added, "
            f"{result.duplicates_found} duplicates, {len(result.errors)} errors"
        )
        return result
