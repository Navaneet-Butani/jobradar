"""Hirist fetcher service — searches by keyword (location text doesn't filter,
see config.py), paginates each term, and runs everything through the ingest
pipeline. Search terms come from the active job profiles (app/services/search_targets.py).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from .client import HiristClient
from .config import build_source_config
from ...services.search_targets import load_search_targets
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

MAX_PAGES_PER_TERM = 5  # size=200/page -> up to 1,000 per term. First live test used 10 pages/term
                        # (20k raw records across all terms) and took 45+ minutes — too long for a
                        # scheduled daily run given how much cross-term overlap gets deduped anyway.


@dataclass
class FetchResult:
    success: bool
    terms_searched: int = 0
    jobs_seen: int = 0
    jobs_processed: int = 0
    jobs_added: int = 0
    duplicates_found: int = 0
    errors: List[str] = field(default_factory=list)


def _normalize(job: Dict[str, Any]) -> Dict[str, Any]:
    """Hirist-specific quirks: tags[] -> flat skill names, locations[] + workFromHome
    -> location text, epoch-ms -> ISO date, hidden salary -> null (not zero)."""
    normalized = dict(job)

    tags = job.get('tags') or []
    normalized['skills'] = [t.get('name') for t in tags if t.get('name')]

    locations = job.get('locations') or []
    loc_names = [l.get('name') for l in locations if l.get('name')]
    # Some postings list dozens of locations ("pan-India, all metros, ...") —
    # location_raw is VARCHAR(255), so cap how many we join rather than truncate mid-string.
    if len(loc_names) > 6:
        location_text = ", ".join(loc_names[:6]) + f" (+{len(loc_names) - 6} more)"
    else:
        location_text = ", ".join(loc_names) if loc_names else (job.get('otherLocation') or "")
    if job.get('workFromHome') and 'remote' not in location_text.lower() and 'anywhere' not in location_text.lower():
        location_text = f"{location_text} (Remote)".strip(", ")
    normalized['location'] = (location_text or "India")[:250]

    created = job.get('createdTime')
    if isinstance(created, (int, float)):
        normalized['createdTime'] = datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()

    if job.get('hideSal'):
        normalized['minSal'] = None
        normalized['maxSal'] = None

    return normalized


class HiristFetcher:
    def __init__(self, source_id: int, client: Optional[HiristClient] = None,
                 job_processor: Optional[JobProcessor] = None):
        self.source_id = source_id
        self.client = client or HiristClient()
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

    async def fetch_jobs(self, terms: Optional[List[str]] = None) -> FetchResult:
        result = FetchResult(success=False)
        terms = terms or (await load_search_targets()).terms

        async with self.client:
            for term in terms:
                result.terms_searched += 1
                page = 0

                while page < MAX_PAGES_PER_TERM:
                    try:
                        hirist_page = await self.client.fetch_page(term, page)
                    except Exception as e:
                        logger.error(f"Error fetching Hirist page (term='{term}', page={page}): {e}")
                        result.errors.append(f"{term}/page {page}: {e}")
                        break

                    if not hirist_page.jobs:
                        break

                    raw_jobs = [
                        RawJobData(
                            source_id=self.source_id,
                            external_id=str(job.get('id')),
                            raw_data=_normalize(job),
                            source_url=job.get('jobDetailUrl'),
                            fetched_at=datetime.utcnow(),
                        )
                        for job in hirist_page.jobs
                        if job.get('id') is not None
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
                        f"Hirist '{term}' page={page}: {len(raw_jobs)} seen, "
                        f"added={result.jobs_added}, duplicates={result.duplicates_found}"
                    )

                    if not hirist_page.has_more:
                        break
                    page += 1

        result.success = len(result.errors) == 0 or result.jobs_added > 0
        logger.info(
            f"Hirist sync complete: {result.terms_searched} terms, {result.jobs_seen} seen, "
            f"{result.jobs_added} added, {result.duplicates_found} duplicates, {len(result.errors)} errors"
        )
        return result
