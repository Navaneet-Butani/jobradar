#!/usr/bin/env python3
"""Push new strong matches to each profile's chat webhook (Telegram/Discord/Slack/ntfy).

    python -m scripts.notify_matches

run_ingest already does this after every ingest; use this to send by hand or
after `scripts.run_matching`. See app/services/notify.py for URL formats.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import db
from app.services.notify import notify_new_matches


async def main() -> None:
    await db.connect()
    try:
        async with db.get_session() as session:
            print(await notify_new_matches(session))
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
