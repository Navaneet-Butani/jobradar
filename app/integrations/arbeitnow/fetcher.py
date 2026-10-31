"""Arbeitnow fetcher service — orchestrates paginated fetch and processing."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from .client import ArbeitnowClient
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

MAX_PAGES = 100  # safety ceiling — current corpus is ~19 pages


@dataclass
class FetchResult:
    success: bool
    pages_fetched: int = 0
    jobs_seen: int = 0
    jobs_processed: int = 0
    jobs_added: int = 0
    duplicates_found: int = 0
    errors: List[str] = field(default_factory=list)


def _normalize(job: Dict[str, Any]) -> Dict[str, Any]:
    """Arbeitnow-specific quirks: unix timestamp -> ISO date, remote flag -> location text
    (the pipeline's remote_scope classifier reads location/description text, not a boolean field)."""
    normalized = dict(job)

    created_at = normalized.get('created_at')
    if isinstance(created_at, (int, float)):
        normalized['created_at'] = datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat()

    if normalized.get('remote') and 'remote' not in (normalized.get('location') or '').lower():
        normalized['location'] = f"{normalized.get('location') or ''} (Remote)".strip()

    return normalized


class ArbeitnowFetcher:
    def __init__(self, source_id: int, client: Optional[ArbeitnowClient] = None,
                 job_processor: Optional[JobProcessor] = None):
        self.source_id = source_id
        self.client = client or ArbeitnowClient()
        self.job_processor = job_processor or self._build_default_job_processor()
        self.source_config = build_source_config(source_id)

    @staticmethod
    def _build_default_job_processor() -> JobProcessor:
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
            validation_service=ValidationService(),
        )

    async def fetch_jobs(self) -> FetchResult:
        result = FetchResult(success=False)

        async with self.client:
            page_num = 1
            while page_num <= MAX_PAGES:
                try:
                    page = await self.client.fetch_page(page_num)
                except Exception as e:
                    logger.error(f"Error fetching Arbeitnow page {page_num}: {e}")
                    result.errors.append(f"Fetch error at page {page_num}: {e}")
                    break

                result.pages_fetched += 1
                if not page.jobs:
                    break

                raw_jobs = [
                    RawJobData(
                        source_id=self.source_id,
                        external_id=str(job.get('slug')),
                        raw_data=_normalize(job),
                        source_url=job.get('url'),
                        fetched_at=datetime.utcnow(),
                    )
                    for job in page.jobs
                    if job.get('slug')
                ]
                result.jobs_seen += len(raw_jobs)

                batch_result: BatchProcessingResult = await self.job_processor.process_job_batch(
                    raw_jobs, self.source_config
                )
                result.jobs_processed += batch_result.successful_jobs
                result.jobs_added += batch_result.new_jobs_added
                result.duplicates_found += batch_result.duplicate_jobs
                if batch_result.errors:
                    result.errors.extend(batch_result.errors)

                logger.info(
                    f"Arbeitnow progress: page={page_num}, added={result.jobs_added}, "
                    f"duplicates={result.duplicates_found}"
                )

                if not page.next_page_url:
                    break
                page_num += 1

        result.success = len(result.errors) == 0 or result.jobs_added > 0
        logger.info(
            f"Arbeitnow sync complete: {result.pages_fetched} pages, {result.jobs_seen} seen, "
            f"{result.jobs_added} added, {result.duplicates_found} duplicates, {len(result.errors)} errors"
        )
        return result
