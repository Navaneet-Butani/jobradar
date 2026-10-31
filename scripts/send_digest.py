#!/usr/bin/env python3
"""Send digest emails — daily new-match digest or weekly stats summary.

Scheduled by .github/workflows/digest.yml (08:00 IST daily, 08:30 IST Monday);
also runnable by hand. Requires EMAIL_TRANSPORT to be configured — `smtp`
(SMTP_HOST/USERNAME/PASSWORD), `resend` (RESEND_API_KEY + SES_FROM_EMAIL), or
`ses` (AWS creds).
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config.settings import settings
from app.core.database import db
from app.services.email.digest import send_daily_digest, send_weekly_summary
from app.services.email.email_service import get_email_service


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["daily", "weekly"], help="Which digest to send")
    args = parser.parse_args()

    if not get_email_service().is_email_configured():
        print(
            f"Email transport '{settings.email_transport}' is not configured. Needs:\n"
            "  smtp   — SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD\n"
            "  resend — RESEND_API_KEY, SES_FROM_EMAIL\n"
            "  ses    — AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, SES_FROM_EMAIL\n"
            "Aborting."
        )
        sys.exit(1)

    await db.connect()
    try:
        async with db.get_session() as session:
            if args.kind == "daily":
                stats = await send_daily_digest(session)
            else:
                stats = await send_weekly_summary(session)
    finally:
        await db.disconnect()

    print(f"{args.kind} digest: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
