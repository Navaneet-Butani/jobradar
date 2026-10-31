#!/usr/bin/env python3
"""Print table sizes so it's easy to watch usage against Supabase's 500 MB free tier."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.core.database import db

# `total - heap` is NOT the index size: it also contains TOAST, where Postgres
# parks oversized values (raw_data, description, the generated tsvectors).
# Reporting the two as one number is what made the corpus look index-heavy when
# it is really text-heavy — 89 MB of TOAST against 13 MB of actual indexes.
TABLE_SIZES_SQL = """
SELECT
    c.relname AS table_name,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
    pg_size_pretty(pg_relation_size(c.oid)) AS table_size,
    pg_size_pretty(COALESCE(pg_total_relation_size(t.oid), 0)) AS toast_size,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes_size
FROM pg_class c
LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_class t ON t.oid = c.reltoastrelid
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY pg_total_relation_size(c.oid) DESC
"""

TOTAL_SIZE_SQL = "SELECT pg_size_pretty(pg_database_size(current_database()))"


async def main():
    await db.connect()
    session = db.session
    try:
        rows = (await session.execute(text(TABLE_SIZES_SQL))).all()
        total = (await session.execute(text(TOTAL_SIZE_SQL))).scalar_one()

        print(f"Database total size: {total} (Supabase free tier limit: 500 MB)")
        print()
        print(f"{'Table':<35} {'Total':>12} {'Heap':>12} {'TOAST':>12} {'Indexes':>12}")
        print("-" * 86)
        for row in rows:
            print(f"{row.table_name:<35} {row.total_size:>12} {row.table_size:>12} "
                  f"{row.toast_size:>12} {row.indexes_size:>12}")
    finally:
        await session.close()
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
