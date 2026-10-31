#!/usr/bin/env python3
"""Single entrypoint for scheduled ingest (GitHub Actions replaces an
always-on worker; see docs/self-hosting.md).

Usage:
    python -m scripts.run_ingest --sources instahyre,ats,jobspy,remoteok

Runs each requested source's full fetch through the ingest pipeline and
prints a per-source summary (fetched / new / duplicate / errors). Exits
non-zero only if every requested source failed outright.
"""

import asyncio
import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

# Ingest processes ~10 jobs concurrently (one DB session per asyncio task); the
# API's default 3+2 pool starves it into timeouts. Set before settings load.
# An explicit DB_POOL_SIZE / DB_MAX_OVERFLOW in the environment still wins.
# On Supabase this requires the TRANSACTION pooler URI (port 6543).
import os
os.environ.setdefault("DB_POOL_SIZE", "10")
os.environ.setdefault("DB_MAX_OVERFLOW", "10")

from app.core.database import db
from app.core.redis import redis_manager
from app.services.enrichment import backfill_from_raw
from app.services.matching import run_matching

ALL_SOURCES = ['instahyre', 'ats', 'jobspy', 'remoteok', 'arbeitnow', 'remotive', 'himalayas',
               'hirist', 'linkedin']


@dataclass
class SourceSummary:
    source: str
    success: bool
    jobs_seen: int = 0
    jobs_added: int = 0
    duplicates_found: int = 0
    error: Optional[str] = None


async def run_instahyre() -> SourceSummary:
    from app.integrations.instahyre.config import setup_instahyre_source
    from app.integrations.instahyre.fetcher import InstahyreFetcher

    try:
        source_id = await setup_instahyre_source()
        result = await InstahyreFetcher(source_id).fetch_jobs()
        return SourceSummary('instahyre', result.success, result.jobs_seen,
                             result.jobs_added, result.duplicates_found,
                             '; '.join(result.errors) if result.errors else None)
    except Exception as e:
        return SourceSummary('instahyre', False, error=str(e))


async def run_ats() -> SourceSummary:
    from app.integrations.ats.config import setup_ats_source
    from app.integrations.ats.fetcher import ATSFetcher

    try:
        source_id = await setup_ats_source()
        fetcher = ATSFetcher(source_id)
        result = await fetcher.poll_all_companies()
        await fetcher.run_discovery(limit=50)
        return SourceSummary('ats', result.success, result.jobs_seen,
                             result.jobs_added, result.duplicates_found,
                             '; '.join(result.errors) if result.errors else None)
    except Exception as e:
        return SourceSummary('ats', False, error=str(e))


async def run_jobspy() -> SourceSummary:
    from app.integrations.jobspy_source.config import setup_jobspy_source
    from app.integrations.jobspy_source.fetcher import JobSpyFetcher

    try:
        source_id = await setup_jobspy_source()
        result = await JobSpyFetcher(source_id).fetch_jobs()
        return SourceSummary('jobspy', result.success, result.jobs_seen,
                             result.jobs_added, result.duplicates_found,
                             '; '.join(result.errors) if result.errors else None)
    except Exception as e:
        return SourceSummary('jobspy', False, error=str(e))


async def run_remoteok() -> SourceSummary:
    from app.integrations.remoteok.config import setup_remoteok_source
    from app.integrations.remoteok.fetcher import RemoteOKFetcher

    try:
        source_id = await setup_remoteok_source()
        fetcher = RemoteOKFetcher()
        fetcher.source_id = source_id
        result = await fetcher.fetch_jobs()
        return SourceSummary('remoteok', result.success, result.stats.total_jobs_found,
                             result.stats.jobs_added, result.stats.duplicates_found,
                             result.error_message)
    except Exception as e:
        return SourceSummary('remoteok', False, error=str(e))


async def run_arbeitnow() -> SourceSummary:
    from app.integrations.arbeitnow.config import setup_arbeitnow_source
    from app.integrations.arbeitnow.fetcher import ArbeitnowFetcher

    try:
        source_id = await setup_arbeitnow_source()
        result = await ArbeitnowFetcher(source_id).fetch_jobs()
        return SourceSummary('arbeitnow', result.success, result.jobs_seen,
                             result.jobs_added, result.duplicates_found,
                             '; '.join(result.errors) if result.errors else None)
    except Exception as e:
        return SourceSummary('arbeitnow', False, error=str(e))


async def run_remotive() -> SourceSummary:
    from app.integrations.remotive.config import setup_remotive_source
    from app.integrations.remotive.fetcher import RemotiveFetcher

    try:
        source_id = await setup_remotive_source()
        result = await RemotiveFetcher(source_id).fetch_jobs()
        return SourceSummary('remotive', result.success, result.jobs_seen,
                             result.jobs_added, result.duplicates_found,
                             '; '.join(result.errors) if result.errors else None)
    except Exception as e:
        return SourceSummary('remotive', False, error=str(e))


async def run_himalayas() -> SourceSummary:
    from app.integrations.himalayas.config import setup_himalayas_source
    from app.integrations.himalayas.fetcher import HimalayasFetcher

    try:
        source_id = await setup_himalayas_source()
        result = await HimalayasFetcher(source_id).fetch_jobs()
        return SourceSummary('himalayas', result.success, result.jobs_seen,
                             result.jobs_added, result.duplicates_found,
                             '; '.join(result.errors) if result.errors else None)
    except Exception as e:
        return SourceSummary('himalayas', False, error=str(e))


async def run_hirist() -> SourceSummary:
    from app.integrations.hirist.config import setup_hirist_source
    from app.integrations.hirist.fetcher import HiristFetcher

    try:
        source_id = await setup_hirist_source()
        result = await HiristFetcher(source_id).fetch_jobs()
        return SourceSummary('hirist', result.success, result.jobs_seen,
                             result.jobs_added, result.duplicates_found,
                             '; '.join(result.errors) if result.errors else None)
    except Exception as e:
        return SourceSummary('hirist', False, error=str(e))


async def run_linkedin() -> SourceSummary:
    from app.integrations.linkedin.config import setup_linkedin_source
    from app.integrations.linkedin.fetcher import LinkedInFetcher

    try:
        source_id = await setup_linkedin_source()
        result = await LinkedInFetcher(source_id).fetch_jobs()
        error = '; '.join(result.errors[:3]) if result.errors else None
        if result.blocked:
            error = f"blocked by LinkedIn after {result.requests_made} requests" + (f"; {error}" if error else "")
        return SourceSummary('linkedin', result.success, result.jobs_seen,
                             result.jobs_added, result.duplicates_found, error)
    except Exception as e:
        return SourceSummary('linkedin', False, error=str(e))


RUNNERS = {
    'instahyre': run_instahyre,
    'ats': run_ats,
    'jobspy': run_jobspy,
    'remoteok': run_remoteok,
    'arbeitnow': run_arbeitnow,
    'remotive': run_remotive,
    'himalayas': run_himalayas,
    'hirist': run_hirist,
    'linkedin': run_linkedin,
}


def print_summary(summaries: list) -> None:
    print()
    print(f"{'Source':<12} {'Status':<8} {'Seen':>8} {'Added':>8} {'Duplicate':>10}")
    print("-" * 50)
    for s in summaries:
        status = "OK" if s.success else "FAILED"
        print(f"{s.source:<12} {status:<8} {s.jobs_seen:>8} {s.jobs_added:>8} {s.duplicates_found:>10}")
        if s.error:
            print(f"  error: {s.error}")
    print()


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run scheduled ingest for one or more sources")
    parser.add_argument('--sources', required=True,
                        help=f"Comma-separated source list, from: {', '.join(ALL_SOURCES)}")
    parser.add_argument('--no-matching', action='store_true',
                        help="Skip the post-ingest matching pass (jobs will land unscored)")
    args = parser.parse_args()

    requested = [s.strip() for s in args.sources.split(',') if s.strip()]
    unknown = [s for s in requested if s not in RUNNERS]
    if unknown:
        print(f"Unknown source(s): {', '.join(unknown)}. Valid: {', '.join(ALL_SOURCES)}")
        return 1

    await db.connect()
    # app/main.py connects Redis in its lifespan, but nothing did here, so the
    # dedup bloom filter and the content-hash cache were silently dead in every
    # scheduled run -- "Error checking bloom filter: 'NoneType' object has no
    # attribute 'sismember'". On localhost that only cost a few milliseconds a
    # job. Against Supabase in Singapore from a US-hosted runner it meant every
    # job paid a full dedup round trip: 1,851 jobs in 40 minutes, and the run
    # hit the job timeout. Redis failures stay non-fatal (core/redis.py), so
    # this is safe even when Upstash is unreachable.
    await redis_manager.connect()
    try:
        # Anchor the incremental match window before fetching, so jobs that
        # land while ingest is still running are picked up rather than missed.
        started_at = datetime.utcnow()

        summaries = []
        for source in requested:
            print(f"Running {source}...")
            summary = await RUNNERS[source]()
            summaries.append(summary)

        print_summary(summaries)
        all_failed = bool(summaries) and all(not s.success for s in summaries)

        # Promote the useful bits of each raw payload into columns (recruiter,
        # applicant counts, company profile). Scoped to rows this run created.
        if not all_failed:
            print("Enriching new rows from their raw payloads...")
            try:
                async with db.get_session() as session:
                    stats = await backfill_from_raw(session, sources=requested, since=started_at)
                print(f"  scanned={stats['scanned']} jobs={stats['jobs_updated']} "
                      f"companies={stats['companies_touched']}")
            except Exception as e:
                # Cosmetic data. Never let it fail an otherwise good ingest.
                print(f"  enrichment failed: {e}")

        # Phase 2 Task 3.5: score what just arrived. Without this, a scheduled
        # ingest adds jobs that nobody ever sees, because the feed only reads
        # the matches table.
        if args.no_matching:
            print("\nSkipping matching (--no-matching).")
        elif all_failed:
            print("\nSkipping matching — every source failed, so there is nothing new to score.")
        else:
            print("\nMatching new jobs against active profiles...")
            try:
                stats = await run_matching(since=started_at)
                if stats:
                    for profile_id, s in stats.items():
                        print(f"  profile {profile_id}: matched={s['matched']} "
                              f"dropped={s['dropped']} pruned={s['pruned']} "
                              f"considered={s['jobs_considered']}")
                else:
                    print("  no active profiles to match against")
            except Exception as e:
                # Ingest succeeded; a matching failure shouldn't discard that work
                # or fail the workflow. Surface it and move on.
                print(f"  matching failed: {e}")

        if all_failed:
            print("All sources failed.")
            return 1
        return 0
    finally:
        await redis_manager.disconnect()
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
