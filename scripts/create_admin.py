#!/usr/bin/env python3
"""Create (or promote) the first admin account.

JobRadar is invite-only: there is no public signup. Run this once after the
database is migrated, log in, then invite everyone else from Settings -> Team.

    python -m scripts.create_admin --email you@example.com --name "Your Name"

Prints a generated password unless --password is given. Re-running for an
existing email promotes it to admin and (with --reset-password) sets a new one.
"""

import argparse
import asyncio
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.core.database import db
from app.core.security import SecurityManager
from app.models import UserDB, UserProfileDB


async def create_admin(email: str, name: str, password: str | None, reset: bool) -> None:
    email = email.strip().lower()
    first, _, last = name.strip().partition(" ")
    await db.connect()
    try:
        async with db.get_session() as session:
            user = (await session.execute(select(UserDB).where(UserDB.email == email))).scalar_one_or_none()
            generated = password is None
            password = password or secrets.token_urlsafe(14)
            if user is None:
                user = UserDB(email=email, password_hash=SecurityManager.hash_password(password),
                              is_active=True, email_verified=True, is_admin=True)
                session.add(user)
                await session.flush()
                session.add(UserProfileDB(user_id=user.id, first_name=first or None, last_name=last or None))
                print(f"Created admin {email}")
            else:
                user.is_admin = True
                user.is_active = True
                if reset:
                    user.password_hash = SecurityManager.hash_password(password)
                print(f"{email} already exists; promoted to admin")
                if not reset:
                    generated = False
            await session.commit()
        if generated:
            print(f"Password (shown once, change it after logging in): {password}")
    finally:
        await db.disconnect()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="Admin")
    p.add_argument("--password", help="omit to generate one")
    p.add_argument("--reset-password", action="store_true", help="for an existing account")
    a = p.parse_args()
    asyncio.run(create_admin(a.email, a.name, a.password, a.reset_password))


if __name__ == "__main__":
    main()
