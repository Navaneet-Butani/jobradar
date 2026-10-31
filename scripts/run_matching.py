#!/usr/bin/env python3
"""Run the matching engine against all active job_profiles.

Full rescore by default (--since is ISO8601, for the post-ingest
incremental mode described in REFERENCE 3.5). LLM re-rank runs
automatically when GEMINI_API_KEY is set; --no-llm forces it off.
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import db
from app.services.matching import run_matching


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", type=str, default=None, help="ISO8601 timestamp; only score jobs first-seen on/after this")
    parser.add_argument("--profile-ids", type=str, default=None, help="Comma-separated job_profile ids; default is all active profiles")
    parser.add_argument("--no-llm", action="store_true", help="Skip the LLM re-rank pass")
    args = parser.parse_args()

    since = datetime.fromisoformat(args.since) if args.since else None
    profile_ids = [int(x) for x in args.profile_ids.split(",")] if args.profile_ids else None

    await db.connect()
    try:
        stats = await run_matching(profile_ids=profile_ids, since=since, llm_rerank=not args.no_llm)
    finally:
        await db.disconnect()

    for profile_id, s in stats.items():
        print(f"profile {profile_id}: matched={s['matched']} dropped={s['dropped']} "
              f"pruned={s['pruned']} considered={s['jobs_considered']}")

    if not stats:
        print("No active profiles matched.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
