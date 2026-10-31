"""Himalayas fetcher service — orchestrates paginated fetch and processing.

The corpus is huge (~100k+ jobs, heavily global) with no server-side
location filter (tested — locationRestrictions param is silently
ignored, same as Instahyre's filter params). Ingesting all of it isn't
affordable on a ₹0/month personal tool, so this caps at MAX_PAGES most
recent jobs and relies on the matching engine's remote_scope classifier
to filter the rest locally.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from .client import HimalayasClient
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

MAX_PAGES = 100  # server caps each response at ~20 jobs regardless of requested limit
                 # (verified live) — 100 pages ≈ 2,000 most-recent jobs, bounded pull


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
    """Himalayas-specific quirks: unix timestamp -> ISO date, location list -> string."""
    normalized = dict(job)

    pub_date = normalized.get('pubDate')
    if isinstance(pub_date, (int, float)):
        normalized['pubDate'] = datetime.fromtimestamp(pub_date, tz=timezone.utc).isoformat()

    locations = normalized.get('locationRestrictions')
    if isinstance(locations, list):
        normalized['locationRestrictions'] = ", ".join(locations) if locations else "Anywhere"

    return normalized


def _external_id(job: Dict[str, Any]) -> Optional[str]:
    """No id/slug field — the guid URL is the closest thing to a stable identifier."""
    guid = job.get('guid')
    return guid.rsplit('/', 1)[-1] if guid else None


class HimalayasFetcher:
    def __init__(self, source_id: int, client: Optional[HimalayasClient] = None,
                 job_processor: Optional[JobProcessor] = None):
        self.source_id = source_id
        self.client = client or HimalayasClient()
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
            offset = 0
            pages = 0

            while pages < MAX_PAGES:
                try:
                    page = await self.client.fetch_page(offset)
                except Exception as e:
                    logger.error(f"Error fetching Himalayas page (offset={offset}): {e}")
                    result.errors.append(f"Fetch error at offset {offset}: {e}")
                    break

                pages += 1
                result.pages_fetched = pages
                if not page.jobs:
                    break

                raw_jobs = [
                    RawJobData(
                        source_id=self.source_id,
                        external_id=_external_id(job),
                        raw_data=_normalize(job),
                        source_url=job.get('applicationLink'),
                        fetched_at=datetime.utcnow(),
                    )
                    for job in page.jobs
                    if _external_id(job)
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
                    f"Himalayas progress: offset={offset}/{page.total_count}, "
                    f"added={result.jobs_added}, duplicates={result.duplicates_found}"
                )

                offset += len(page.jobs)  # server-actual count, not the requested limit — it silently caps lower
                if offset >= page.total_count:
                    break

        result.success = len(result.errors) == 0 or result.jobs_added > 0
        logger.info(
            f"Himalayas sync complete: {result.pages_fetched} pages, {result.jobs_seen} seen, "
            f"{result.jobs_added} added, {result.duplicates_found} duplicates, {len(result.errors)} errors "
            f"(capped at {MAX_PAGES} pages out of a much larger corpus)"
        )
        return result
