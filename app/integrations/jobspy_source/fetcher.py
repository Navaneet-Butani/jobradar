"""JobSpy fetcher — runs the profile-cities x terms search matrix through
Indeed and LinkedIn, plus a remote sweep, and feeds results through the
ingest pipeline. scrape_jobs() is synchronous and slow, so every call
runs in a thread pool executor to avoid blocking the event loop.
"""

import asyncio
import functools
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, Any, List, Optional

import pandas as pd
from jobspy import scrape_jobs

from .config import (
    build_source_config, REMOTE_LOCATION, linkedin_priority_order,
)
from ...services.search_targets import load_search_targets
from .rate_limiter import LinkedInRunTracker
from ...models.source import RawJobData
from ...services.job_processor import JobProcessor
from ...repositories.job_repository import JobRepository
from ...repositories.company_repository import CompanyRepository
from ...services.company_service import CompanyService
from ...services.location_parser import LocationParser
from ...services.salary_parser import SalaryParser
from ...services.skill_extractor import SkillExtractor
from ...services.deduplication_service import DeduplicationService
from ...services.validation_service import ValidationService

logger = logging.getLogger(__name__)

RESULTS_WANTED_PER_SEARCH = 30
HOURS_OLD = 168  # 7 days
LINKEDIN_SEARCHES_PER_RUN = 3  # docs/sources.md: "2-3 runs/day maximum"


@dataclass
class JobSpyFetchResult:
    """Result of a JobSpy sweep across the search matrix."""
    success: bool
    searches_run: int = 0
    searches_skipped_linkedin: int = 0
    jobs_seen: int = 0
    jobs_processed: int = 0
    jobs_added: int = 0
    duplicates_found: int = 0
    errors: List[str] = field(default_factory=list)


class JobSpyFetcher:
    """Runs the JobSpy search matrix (Indeed + LinkedIn) through the ingest pipeline."""

    def __init__(self,
                 source_id: int,
                 job_processor: Optional[JobProcessor] = None,
                 linkedin_tracker: Optional[LinkedInRunTracker] = None):
        self.source_id = source_id
        self.job_processor = job_processor or self._build_default_job_processor()
        self.linkedin_tracker = linkedin_tracker or LinkedInRunTracker()
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

    async def fetch_jobs(self,
                          cities: Optional[List[str]] = None,
                          terms: Optional[List[str]] = None,
                          include_metro: bool = False,
                          include_remote_sweep: bool = True,
                          sites: Optional[List[str]] = None) -> JobSpyFetchResult:
        """Run the search matrix. Defaults to the profiles' cities x titles + a remote sweep."""
        result = JobSpyFetchResult(success=False)
        if cities is None or not terms:
            targets = await load_search_targets()
            if cities is None:
                cities = targets.locations(targets.cities + (targets.metro_cities if include_metro else []))
            terms = terms or targets.terms
        sites = sites or ['indeed', 'linkedin']

        searches = [(city, term) for city in cities for term in terms]
        if include_remote_sweep:
            # Remote sweep uses is_remote=True instead of a specific city.
            searches += [(None, term) for term in terms]

        # LinkedIn gets a small, rotating slice of this sweep's searches — primary
        # cities first, remote after (see config.linkedin_priority_order). A plain
        # per-search cooldown would always land on the same first entry, forever;
        # the rotation offset instead cycles which (city, term) pairs get LinkedIn
        # coverage across successive runs.
        linkedin_targets: set = set()
        linkedin_used_this_run = False
        if 'linkedin' in sites:
            if await self.linkedin_tracker.can_run_now():
                priority = linkedin_priority_order(cities, terms) if include_remote_sweep else \
                    [(city, term) for city in cities for term in terms]
                if priority:
                    offset = await self.linkedin_tracker.next_rotation_offset(
                        len(priority), advance_by=LINKEDIN_SEARCHES_PER_RUN
                    )
                    for i in range(min(LINKEDIN_SEARCHES_PER_RUN, len(priority))):
                        linkedin_targets.add(priority[(offset + i) % len(priority)])
            else:
                result.searches_skipped_linkedin = len(searches)

        for city, term in searches:
            active_sites = [s for s in sites if s != 'linkedin']
            if (city, term) in linkedin_targets:
                active_sites.append('linkedin')

            if not active_sites:
                continue

            try:
                df = await self._scrape(active_sites, term, city)
            except Exception as e:
                logger.error(f"JobSpy scrape failed for term='{term}' city='{city}': {e}")
                result.errors.append(f"{term}/{city}: {e}")
                continue

            result.searches_run += 1
            if 'linkedin' in active_sites:
                linkedin_used_this_run = True

            if df is None or df.empty:
                continue

            raw_jobs = self._rows_to_raw_jobs(df)
            result.jobs_seen += len(raw_jobs)

            batch_result = await self.job_processor.process_job_batch(raw_jobs, self.source_config)
            result.jobs_processed += batch_result.successful_jobs
            result.jobs_added += batch_result.new_jobs_added
            result.duplicates_found += batch_result.duplicate_jobs
            if batch_result.errors:
                result.errors.extend(batch_result.errors)

            logger.info(
                f"JobSpy '{term}' @ {city or 'remote'}: {len(raw_jobs)} seen, "
                f"{batch_result.new_jobs_added} added (running total: {result.jobs_added})"
            )

        if linkedin_used_this_run:
            await self.linkedin_tracker.record_run()

        result.success = True
        logger.info(
            f"JobSpy sweep complete: {result.searches_run} searches "
            f"({result.searches_skipped_linkedin} skipped LinkedIn), "
            f"{result.jobs_seen} seen, {result.jobs_added} added, "
            f"{result.duplicates_found} duplicates, {len(result.errors)} errors"
        )
        return result

    async def _scrape(self, sites: List[str], term: str, city: Optional[str]) -> pd.DataFrame:
        """Run the blocking scrape_jobs() call in a thread pool executor."""
        kwargs = dict(
            site_name=sites,
            search_term=term,
            results_wanted=RESULTS_WANTED_PER_SEARCH,
            hours_old=HOURS_OLD,
            country_indeed="India",
            linkedin_fetch_description=False,  # bulk sweep — costs +1 request/job otherwise
            verbose=0,
        )
        if city:
            kwargs['location'] = city
        else:
            kwargs['location'] = REMOTE_LOCATION
            kwargs['is_remote'] = True

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(scrape_jobs, **kwargs))

    def _rows_to_raw_jobs(self, df: pd.DataFrame) -> List[RawJobData]:
        raw_jobs = []
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            external_id = row_dict.get('id')
            if not external_id:
                continue

            raw_data = {k: self._json_safe(v) for k, v in row_dict.items()}
            raw_jobs.append(RawJobData(
                source_id=self.source_id,
                external_id=str(external_id),
                raw_data=raw_data,
                source_url=raw_data.get('job_url_direct') or raw_data.get('job_url'),
                fetched_at=datetime.utcnow(),
            ))
        return raw_jobs

    @staticmethod
    def _json_safe(value: Any) -> Any:
        """DataFrame cells can hold NaN/NaT/date objects that don't round-trip cleanly
        through the rest of the pipeline (Pydantic dicts, eventual JSONB storage)."""
        if isinstance(value, float) and math.isnan(value):
            return None
        if isinstance(value, date):
            return value.isoformat()
        if pd.isna(value) if not isinstance(value, (list, dict)) else False:
            return None
        return value
