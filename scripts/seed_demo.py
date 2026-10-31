#!/usr/bin/env python3
"""Seed a demo account with two example job profiles.

    python -m scripts.seed_demo
    python -m scripts.run_ingest --sources ats,remotive,himalayas   # no API keys needed

Both profiles are realistic starting points to copy from: a senior backend
engineer and a junior frontend developer. Edit them on the Profile page, or
delete the demo account once you've created your own with
`scripts.create_admin`. Re-runnable: existing user/profile rows are skipped.
"""

import asyncio
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.core.database import db
from app.core.security import SecurityManager
from app.models import JobProfileDB, UserDB, UserProfileDB

DEMO_EMAIL = "demo@example.com"

COMMON_EXCLUDES = ["bpo", "voice process", "night shift", "field sales", "data entry", "manual testing"]

PROFILES = [
    {
        "name": "Senior Backend Engineer — Bengaluru / Remote",
        "years_exp": 6.0,
        "seniority_floor": "mid",
        "seniority_ceiling": None,
        "must_have_skills": ["node.js", "python", "postgresql"],
        "nice_to_have_skills": ["typescript", "nestjs", "redis", "kafka", "docker", "aws", "microservices"],
        "target_titles": [
            "Senior Software Engineer", "Senior Backend Engineer", "Backend Developer",
            "Senior Node.js Developer", "Senior Python Developer", "SDE III", "Tech Lead",
        ],
        "cities": ["Bengaluru"],
        "metro_cities": ["Hyderabad", "Pune"],
        "accepts_remote": True,
        "remote_only": False,
        "remote_scope": "india_only",
        "min_salary_inr": 2_000_000,
        "exclude_companies": [],
        "exclude_keywords": ["intern", "internship", "fresher", "trainee", *COMMON_EXCLUDES],
        "include_staffing": False,
        "domain_keywords": ["fintech", "payments", "saas"],
        "no_cs_degree": False,
    },
    {
        "name": "Frontend Developer — Pune / Remote",
        "years_exp": 2.0,
        "seniority_floor": "junior",
        "seniority_ceiling": "mid",
        "must_have_skills": ["react"],
        "nice_to_have_skills": ["next.js", "typescript", "javascript", "tailwind css", "redux", "html", "css"],
        "target_titles": [
            "Frontend Developer", "React Developer", "React.js Developer", "Next.js Developer",
            "UI Developer", "Frontend Engineer", "Software Engineer", "SDE I",
        ],
        "cities": ["Pune"],
        "metro_cities": ["Mumbai", "Bengaluru"],
        "accepts_remote": True,
        "remote_only": False,
        "remote_scope": "india_only",
        "min_salary_inr": 500_000,
        "exclude_companies": [],
        "exclude_keywords": ["senior", "lead", "architect", "principal", "manager", "5+ years", *COMMON_EXCLUDES],
        "include_staffing": False,
        "domain_keywords": [],
        "no_cs_degree": True,
    },
]


async def seed() -> None:
    await db.connect()
    try:
        async with db.get_session() as session:
            user = (await session.execute(select(UserDB).where(UserDB.email == DEMO_EMAIL))).scalar_one_or_none()
            if user is None:
                password = secrets.token_urlsafe(12)
                user = UserDB(email=DEMO_EMAIL, password_hash=SecurityManager.hash_password(password),
                              is_active=True, email_verified=True, is_admin=False)
                session.add(user)
                await session.flush()
                session.add(UserProfileDB(user_id=user.id, first_name="Demo", last_name="User"))
                print(f"Created {DEMO_EMAIL} — password: {password}")
            else:
                print(f"{DEMO_EMAIL} already exists")

            for data in PROFILES:
                exists = (await session.execute(select(JobProfileDB.id).where(
                    JobProfileDB.user_id == user.id, JobProfileDB.name == data["name"]))).scalar_one_or_none()
                if exists:
                    print(f"  profile exists: {data['name']}")
                    continue
                session.add(JobProfileDB(user_id=user.id, **data))
                print(f"  + profile: {data['name']}")
            await session.commit()
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(seed())
