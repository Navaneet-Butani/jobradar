"""Remotive fetcher service — single-request fetch (no pagination) and processing."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .client import RemotiveClient
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


@dataclass
class FetchResult:
    success: bool
    jobs_seen: int = 0
    jobs_processed: int = 0
    jobs_added: int = 0
    duplicates_found: int = 0
    errors: List[str] = field(default_factory=list)


class RemotiveFetcher:
    def __init__(self, source_id: int, client: Optional[RemotiveClient] = None,
                 job_processor: Optional[JobProcessor] = None):
        self.source_id = source_id
        self.client = client or RemotiveClient()
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
            try:
                page = await self.client.fetch_all()
            except Exception as e:
                logger.error(f"Error fetching Remotive jobs: {e}")
                result.errors.append(f"Fetch error: {e}")
                result.success = False
                return result

            raw_jobs = [
                RawJobData(
                    source_id=self.source_id,
                    external_id=str(job.get('id')),
                    raw_data=job,
                    source_url=job.get('url'),
                    fetched_at=datetime.utcnow(),
                )
                for job in page.jobs
                if job.get('id') is not None
            ]
            result.jobs_seen = len(raw_jobs)

            if raw_jobs:
                batch_result: BatchProcessingResult = await self.job_processor.process_job_batch(
                    raw_jobs, self.source_config
                )
                result.jobs_processed = batch_result.successful_jobs
                result.jobs_added = batch_result.new_jobs_added
                result.duplicates_found = batch_result.duplicate_jobs
                if batch_result.errors:
                    result.errors.extend(batch_result.errors)

        result.success = len(result.errors) == 0 or result.jobs_added > 0
        logger.info(
            f"Remotive sync complete: {result.jobs_seen} seen, {result.jobs_added} added, "
            f"{result.duplicates_found} duplicates, {len(result.errors)} errors"
        )
        return result
