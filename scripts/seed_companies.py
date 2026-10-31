#!/usr/bin/env python3
"""Seed companies from data/companies.csv to bootstrap ATS polling.

    python -m scripts.seed_companies [--file data/companies.csv]

Columns: name, ats_type (greenhouse | lever | ashby, optional), ats_slug,
region (free text, informational). Rows with an ATS board are polled on the
next `run_ingest --sources ats`; rows without one get auto-discovered.

Re-runnable: companies that already exist by name are left alone, except that
a missing ATS board is filled in from the file. Add your own companies to the
CSV, and send a pull request so everyone's coverage grows.
"""

import argparse
import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import db
from app.repositories.company_repository import CompanyRepository

DEFAULT_FILE = Path(__file__).parent.parent / "data" / "companies.csv"
ATS_TYPES = {"greenhouse", "lever", "ashby"}


def read_rows(path: Path):
    with open(path, encoding="utf-8", newline="") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            name = (row.get("name") or "").strip()
            ats_type = (row.get("ats_type") or "").strip().lower()
            ats_slug = (row.get("ats_slug") or "").strip()
            if not name:
                continue
            if ats_type and (ats_type not in ATS_TYPES or not ats_slug):
                print(f"  ! line {line_no}: ignoring ATS for {name!r} (type={ats_type!r}, slug={ats_slug!r})")
                ats_type = ats_slug = ""
            yield name, ats_type, ats_slug


async def seed(path: Path) -> None:
    repo = CompanyRepository()
    created = updated = skipped = 0
    for name, ats_type, ats_slug in read_rows(path):
        ats = {"ats_type": ats_type, "ats_slug": ats_slug, "ats_is_active": True} if ats_type else {}
        existing = await repo.get_by_name(name)
        if existing:
            if ats and not existing.ats_type:
                await repo.update(existing.id, ats)
                updated += 1
            else:
                skipped += 1
            continue
        await repo.create_with_slug({"name": name, **ats})
        created += 1
        print(f"  + {name}" + (f" ({ats_type}/{ats_slug})" if ats else ""))
    print(f"\n{created} created, {updated} given an ATS board, {skipped} unchanged")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed companies from a CSV file")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    args = parser.parse_args()
    await db.connect()
    try:
        await seed(args.file)
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
