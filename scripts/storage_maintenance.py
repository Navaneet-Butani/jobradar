#!/usr/bin/env python3
"""Storage-size guardrails for the Supabase free tier (500 MB).

Two maintenance passes, both skipping jobs saved by a user (and, once
Phase 2 adds a matches table, jobs referenced by a match):

  purge-stale     delete jobs whose last_seen_at is older than 60 days
  clear-raw-data  null out job_details.raw_data once it's older than the
                  7-day debugging window (description/requirements are kept)
"""

import asyncio
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.core.database import db

PURGE_AFTER_DAYS = 60
RAW_DATA_AFTER_DAYS = 7

# Never purge a job a user has any relationship with. `matches.job_id` and
# `applications.job_id` are both ON DELETE CASCADE, so deleting a stale job
# would silently take the user's feed state and their whole application
# history with it — including applications they're still waiting to hear back
# on, whose posting naturally stops appearing after 60 days.
KEEP_EXCEPTION_SQL = """
    id NOT IN (SELECT job_id FROM matches)
    AND id NOT IN (SELECT job_id FROM applications)
"""


async def purge_stale_jobs(dry_run: bool) -> int:
    """Delete jobs not seen in over PURGE_AFTER_DAYS days. Cascades to
    job_details etc via FK ondelete=CASCADE."""
    session = db.session
    try:
        count_result = await session.execute(text(
            f"SELECT count(*) FROM jobs "
            f"WHERE last_seen_at < now() - interval '{PURGE_AFTER_DAYS} days' "
            f"AND {KEEP_EXCEPTION_SQL}"
        ))
        count = count_result.scalar_one()

        if dry_run:
            print(f"[dry-run] would delete {count} jobs older than {PURGE_AFTER_DAYS} days")
            return count

        if count:
            await session.execute(text(
                f"DELETE FROM jobs "
                f"WHERE last_seen_at < now() - interval '{PURGE_AFTER_DAYS} days' "
                f"AND {KEEP_EXCEPTION_SQL}"
            ))
            await session.commit()

        print(f"Deleted {count} jobs older than {PURGE_AFTER_DAYS} days")
        return count
    finally:
        await session.close()


async def clear_stale_raw_data(dry_run: bool) -> int:
    """Null job_details.raw_data for jobs first seen over RAW_DATA_AFTER_DAYS
    days ago. Description/requirements/responsibilities are left intact."""
    session = db.session
    try:
        count_result = await session.execute(text(
            f"SELECT count(*) FROM job_details jd "
            f"JOIN jobs j ON j.id = jd.job_id "
            f"WHERE j.first_seen_at < now() - interval '{RAW_DATA_AFTER_DAYS} days' "
            f"AND jd.raw_data IS NOT NULL "
            f"AND j.{KEEP_EXCEPTION_SQL}"
        ))
        count = count_result.scalar_one()

        if dry_run:
            print(f"[dry-run] would null raw_data for {count} job_details rows older than {RAW_DATA_AFTER_DAYS} days")
            return count

        if count:
            await session.execute(text(
                f"UPDATE job_details SET raw_data = NULL "
                f"WHERE job_id IN ("
                f"  SELECT j.id FROM jobs j "
                f"  WHERE j.first_seen_at < now() - interval '{RAW_DATA_AFTER_DAYS} days' "
                f"  AND j.{KEEP_EXCEPTION_SQL}"
                f") AND raw_data IS NOT NULL"
            ))
            await session.commit()

        print(f"Nulled raw_data for {count} job_details rows older than {RAW_DATA_AFTER_DAYS} days")
        return count
    finally:
        await session.close()


async def main():
    parser = argparse.ArgumentParser(description="Run storage-size guardrail maintenance")
    parser.add_argument('command', choices=['purge-stale', 'clear-raw-data', 'run-all'],
                        help='Which maintenance pass to run')
    parser.add_argument('--dry-run', action='store_true', help='Report counts without modifying data')
    args = parser.parse_args()

    await db.connect()
    try:
        if args.command == 'purge-stale':
            await purge_stale_jobs(args.dry_run)
        elif args.command == 'clear-raw-data':
            await clear_stale_raw_data(args.dry_run)
        elif args.command == 'run-all':
            await purge_stale_jobs(args.dry_run)
            await clear_stale_raw_data(args.dry_run)
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
