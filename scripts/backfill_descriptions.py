#!/usr/bin/env python3
"""Fetch descriptions for jobs whose source feed omitted them.

Only Hirist is recoverable — see app/services/enrichment/descriptions.py for
why Instahyre is not. Newest jobs are fetched first, so a bounded run always
covers what someone is most likely to open.

Usage:
    python -m scripts.backfill_descriptions --limit 500
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import db
from app.services.enrichment.descriptions import FETCHABLE_SOURCES, backfill_descriptions


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='hirist', choices=list(FETCHABLE_SOURCES))
    parser.add_argument('--limit', type=int, default=200,
                        help="Max jobs to fetch this run (the source is rate limited to ~2/s)")
    args = parser.parse_args()

    await db.connect()
    try:
        async with db.get_session() as session:
            stats = await backfill_descriptions(session, source=args.source, limit=args.limit)
    finally:
        await db.disconnect()

    print(f"{args.source}: considered {stats['considered']}, fetched {stats['fetched']}, "
          f"stored {stats['stored']}, experience corrected {stats.get('experience_updated', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
