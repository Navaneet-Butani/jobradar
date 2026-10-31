#!/usr/bin/env python3
"""Backfill job and company columns from stored raw payloads.

No network calls — everything comes out of `job_details.raw_data`, which the
pipeline has been storing all along (ground rule 5). Existing values are never
overwritten, except the experience range, where a figure the source states
outright replaces one this codebase inferred. Safe to re-run either way.

Usage:
    python -m scripts.enrich_from_raw                      # every supported source
    python -m scripts.enrich_from_raw --sources hirist     # one source
    python -m scripts.enrich_from_raw --dry-run            # count, change nothing
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import db
from app.services.enrichment.raw_backfill import SUPPORTED_SOURCES, backfill_from_raw


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', default=None,
                        help=f"Comma-separated, from: {', '.join(SUPPORTED_SOURCES)}")
    parser.add_argument('--since', default=None,
                        help="ISO8601; only jobs first seen on or after this")
    parser.add_argument('--limit', type=int, default=None, help="Stop after N jobs")
    parser.add_argument('--dry-run', action='store_true', help="Report only")
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(',')] if args.sources else None
    since = datetime.fromisoformat(args.since) if args.since else None

    await db.connect()
    try:
        async with db.get_session() as session:
            stats = await backfill_from_raw(
                session, sources=sources, since=since, limit=args.limit, dry_run=args.dry_run,
            )
    finally:
        await db.disconnect()

    prefix = "would update" if args.dry_run else "updated"
    print(f"scanned {stats['scanned']} jobs; {prefix} {stats['jobs_updated']} jobs "
          f"and {stats['companies_touched']} companies")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
