"""LinkedIn fetcher — walks the (city, term) matrix through the guest search
endpoint and feeds every page straight into the ingest pipeline.

Bounded by a **request budget per run**, not by a job count. A run stops when
it has spent its budget, exhausted the matrix slice it was given, or been told
to stop (429). At ~3s per request a 300-request budget is ~15 minutes of an
Actions job and, at 10 cards per response, up to ~3,000 raw jobs.

Rotation matters as much as the budget: the matrix is ~150 (city, term) pairs
and one run can only cover a handful, so the starting offset is persisted and
advanced every run. Without it the first few pairs would be the only ones ever
searched.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

from .client import LinkedInClient, LinkedInBlockedError, MAX_START, PAGE_STEP
from .config import REMOTE_LOCATION, build_source_config, search_matrix
from ...services.search_targets import load_search_targets
from ..jobspy_source.rate_limiter import LinkedInRunTracker
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

REQUEST_BUDGET_PER_RUN = 300      # ~15 min at 3s/request
MAX_PAGES_PER_QUERY = 30          # 300 jobs per (city, term) before moving on
POSTED_WITHIN_SECONDS = 30 * 24 * 3600


@dataclass
class FetchResult:
    success: bool
    queries_run: int = 0
    requests_made: int = 0
    jobs_seen: int = 0
    jobs_processed: int = 0
    jobs_added: int = 0
    duplicates_found: int = 0
    blocked: bool = False
    errors: List[str] = field(default_factory=list)


class LinkedInFetcher:
    def __init__(self, source_id: int, client: Optional[LinkedInClient] = None,
                 job_processor: Optional[JobProcessor] = None,
                 run_tracker: Optional[LinkedInRunTracker] = None):
        self.source_id = source_id
        self.client = client or LinkedInClient()
        self.job_processor = job_processor or self._build_default_job_processor()
        self.run_tracker = run_tracker or LinkedInRunTracker()
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

    async def fetch_jobs(self, budget: int = REQUEST_BUDGET_PER_RUN) -> FetchResult:
        result = FetchResult(success=False)
        matrix = search_matrix(await load_search_targets())
        if not matrix:
            result.success = True
            return result
        offset = await self.run_tracker.next_rotation_offset(len(matrix), advance_by=1)
        ordered = matrix[offset:] + matrix[:offset]

        logger.info(
            f"LinkedIn sweep starting at matrix offset {offset}/{len(matrix)} "
            f"with a budget of {budget} requests"
        )

        async with self.client:
            for city, term in ordered:
                if result.requests_made >= budget or result.blocked:
                    break

                result.queries_run += 1
                remaining = budget - result.requests_made
                await self._run_query(city, term, remaining, result)

        await self.run_tracker.record_run()

        result.success = not result.blocked and (result.jobs_added > 0 or not result.errors)
        logger.info(
            f"LinkedIn sweep complete: {result.queries_run} queries, {result.requests_made} requests, "
            f"{result.jobs_seen} seen, {result.jobs_added} added, "
            f"{result.duplicates_found} duplicates, blocked={result.blocked}, {len(result.errors)} errors"
        )
        return result

    async def _run_query(self, city: Optional[str], term: str, remaining: int, result: FetchResult) -> None:
        """Page one (city, term) pair until it runs dry, hits the cap, or the
        budget for this query is spent."""
        location = city or REMOTE_LOCATION
        label = f"'{term}' @ {city or 'India-remote'}"
        pages = min(MAX_PAGES_PER_QUERY, remaining)

        for page in range(pages):
            start = page * PAGE_STEP
            if start >= MAX_START:
                break

            try:
                cards = await self.client.search_page(
                    term, location, start,
                    seconds_old=POSTED_WITHIN_SECONDS,
                    remote_only=city is None,
                )
            except LinkedInBlockedError as e:
                # A block is a signal about the whole run, not this query.
                logger.warning(f"LinkedIn blocked us during {label}: {e}")
                result.blocked = True
                result.errors.append(f"blocked at {label} start={start}")
                return
            except Exception as e:
                logger.error(f"LinkedIn search error {label} start={start}: {e}")
                result.errors.append(f"{label} start={start}: {e}")
                return
            finally:
                result.requests_made += 1

            if not cards:
                return

            raw_jobs = [
                RawJobData(
                    source_id=self.source_id,
                    external_id=card["job_id"],
                    raw_data=card,
                    source_url=card.get("job_url"),
                    fetched_at=datetime.utcnow(),
                )
                for card in cards
                if card.get("job_id") and card.get("title")
            ]
            result.jobs_seen += len(raw_jobs)
            if not raw_jobs:
                continue

            batch: BatchProcessingResult = await self.job_processor.process_job_batch(
                raw_jobs, self.source_config
            )
            result.jobs_processed += batch.successful_jobs
            result.jobs_added += batch.new_jobs_added
            result.duplicates_found += batch.duplicate_jobs
            if batch.errors:
                result.errors.extend(batch.errors)

            logger.info(
                f"LinkedIn {label} start={start}: {len(raw_jobs)} seen, "
                f"added={result.jobs_added}, duplicates={result.duplicates_found}"
            )
