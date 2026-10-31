"""ATS fetcher service — polls every company with a known Greenhouse/Lever/Ashby
board, plus runs auto-discovery for companies that don't have one yet."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional

from .client import ATSClient, ATSAPIError
from .greenhouse import fetch_greenhouse_jobs
from .lever import fetch_lever_jobs
from .ashby import fetch_ashby_jobs
from .discovery import discover_and_save_ats
from .config import build_source_config
from ...models.source import RawJobData
from ...models import CompanyDB
from ...services.job_processor import JobProcessor
from ...repositories.job_repository import JobRepository
from ...repositories.company_repository import CompanyRepository
from ...services.company_service import CompanyService
from ...services.location_parser import LocationParser
from ...core.database import db
from ...services.role_filter import is_it_role
from ...services.scraping_config import get_enabled_categories
from ...services.salary_parser import SalaryParser
from ...services.skill_extractor import SkillExtractor
from ...services.deduplication_service import DeduplicationService
from ...services.validation_service import ValidationService

logger = logging.getLogger(__name__)

PROVIDER_FETCHERS = {
    'greenhouse': fetch_greenhouse_jobs,
    'lever': fetch_lever_jobs,
    'ashby': fetch_ashby_jobs,
}


@dataclass
class ATSFetchResult:
    """Result of an ATS polling run."""
    success: bool
    companies_polled: int = 0
    companies_discovered: int = 0
    jobs_seen: int = 0
    jobs_skipped_non_it: int = 0
    jobs_processed: int = 0
    jobs_added: int = 0
    duplicates_found: int = 0
    errors: List[str] = field(default_factory=list)


class ATSFetcher:
    """Polls all ATS-enabled companies and runs discovery for the rest."""

    def __init__(self,
                 source_id: int,
                 client: Optional[ATSClient] = None,
                 job_processor: Optional[JobProcessor] = None,
                 company_repository: Optional[CompanyRepository] = None):
        self.source_id = source_id
        self.client = client or ATSClient()
        self.company_repository = company_repository or CompanyRepository()
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
            validation_service=ValidationService()
        )

    async def poll_all_companies(self) -> ATSFetchResult:
        """Poll every ATS-enabled company's board and process its jobs."""
        result = ATSFetchResult(success=False)
        companies = await self.company_repository.get_ats_enabled_companies()

        # Read once per run, not per company: the enabled set is one row and
        # every board is filtered against the same answer.
        async with db.get_session() as session:
            self._enabled_categories = await get_enabled_categories(session)
        logger.info(f"ATS collecting role categories: {', '.join(self._enabled_categories)}")

        async with self.client:
            for company in companies:
                try:
                    await self._poll_company(company, result)
                except Exception as e:
                    logger.error(f"Error polling {company.ats_type}/{company.ats_slug} ({company.name}): {e}")
                    result.errors.append(f"{company.name}: {e}")

        result.success = True
        logger.info(
            f"ATS poll complete: {result.companies_polled} companies, "
            f"{result.jobs_seen} seen, {result.jobs_added} added, "
            f"{result.jobs_skipped_non_it} skipped as out-of-scope roles, "
            f"{result.duplicates_found} duplicates, {len(result.errors)} errors"
        )
        return result

    async def _poll_company(self, company: CompanyDB, result: ATSFetchResult) -> None:
        fetch_fn = PROVIDER_FETCHERS.get(company.ats_type)
        if fetch_fn is None:
            logger.warning(f"Unknown ats_type '{company.ats_type}' for company {company.name}, skipping")
            return

        raw_objects = await fetch_fn(self.client, company.ats_slug, company.name)
        result.companies_polled += 1
        await self.company_repository.update(company.id, {'ats_last_polled_at': datetime.utcnow()})

        if not raw_objects:
            return

        # An ATS board is the whole company, not its engineering org: one real
        # run brought back 1,948 postings of which 526 were recruiters, account
        # executives and field-sales agents. They cost storage and processing
        # and can never match any profile, so they are dropped here rather
        # than stored and rejected later. Greenhouse/Ashby key the title as
        # "title", Lever as "text" (see config.build_source_config).
        in_scope = [
            obj for obj in raw_objects
            if obj.get('id') is not None
            and is_it_role(obj.get('title') or obj.get('text') or '',
                           getattr(self, '_enabled_categories', None))
        ]
        skipped = len([o for o in raw_objects if o.get('id') is not None]) - len(in_scope)
        result.jobs_skipped_non_it += skipped

        raw_jobs = [
            RawJobData(
                source_id=self.source_id,
                external_id=f"{company.ats_type}:{obj.get('id')}",
                raw_data=obj,
                source_url=obj.get('_apply_url'),
                fetched_at=datetime.utcnow(),
            )
            for obj in in_scope
        ]
        result.jobs_seen += len(raw_jobs)

        batch_result = await self.job_processor.process_job_batch(raw_jobs, self.source_config)
        result.jobs_processed += batch_result.successful_jobs
        result.jobs_added += batch_result.new_jobs_added
        result.duplicates_found += batch_result.duplicate_jobs
        if batch_result.errors:
            result.errors.extend(batch_result.errors)

    async def run_discovery(self, limit: int = 50) -> int:
        """Probe companies without a known ATS board. Returns count of new hits."""
        candidates = await self.company_repository.get_companies_without_ats_discovery(limit=limit)
        discovered = 0

        async with self.client:
            for company in candidates:
                try:
                    hit = await discover_and_save_ats(
                        company.id, company.name,
                        client=self.client, company_repo=self.company_repository
                    )
                    if hit:
                        discovered += 1
                except ATSAPIError as e:
                    logger.warning(f"Discovery error for '{company.name}': {e}")

        logger.info(f"ATS discovery: {discovered}/{len(candidates)} companies matched")
        return discovered
