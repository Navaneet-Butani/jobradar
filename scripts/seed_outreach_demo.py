#!/usr/bin/env python3
"""Seed fake outreach data so the Outreach page can be reviewed end-to-end.

None of this ever touched a mail server. It exists so you can see what a
campaign looks like once replies and bounces have come back, without waiting
days for real ones.

Everything it creates is tagged in the DB and removable in one command:

    python -m scripts.seed_outreach_demo              # create
    python -m scripts.seed_outreach_demo --purge      # remove
    python -m scripts.seed_outreach_demo --email x@y  # other user

The sending account it creates has a PLACEHOLDER password. Sending will fail
with an authentication error until you replace it with a real Gmail App
Password on the Outreach page. That is deliberate — seeded data must never be
able to email a real person.
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete, select

from app.core.database import db
from app.models import (
    OutreachCampaignDB,
    OutreachContactDB,
    OutreachMessageDB,
    UserDB,
    UserEmailAccountDB,
)
from app.services.outreach.crypto import encrypt_secret

DEFAULT_EMAIL = "demo@example.com"  # created by scripts.seed_demo

# Marks every seeded row so --purge can find them again with no guesswork.
DEMO_TAG = "[demo]"
DEMO_CAMPAIGN_NAME = f"{DEMO_TAG} Bengaluru backend roles"
PLACEHOLDER_PASSWORD = "placeholder-replace-me"

CONTACTS = [
    # (email, name, company, title, role_hint)
    ("priya.sharma@acmesystems.example", "Priya Sharma", "Acme Systems", "HR Manager", "Senior Backend Engineer"),
    ("hr@tatvalabs.example", None, "Tatva Labs", None, "Node.js Developer"),
    ("rahul.m@zenithtech.example", "Rahul Menon", "Zenith Tech", "Talent Lead", "Staff Engineer"),
    ("careers@bluegrid.example", None, "BlueGrid Analytics", None, "Backend Engineer"),
    ("neha.p@corvustech.example", "Neha Patel", "Corvus Tech", "Technical Recruiter", "Senior Full Stack Engineer"),
    ("talent@finlynx.example", None, "Finlynx", None, "Backend Engineer (Fintech)"),
    ("hiring@quantabase.example", "Arjun Rao", "Quantabase", "Engineering Manager", "Platform Engineer"),
    ("hr@nimbusworks.example", "Sneha Joshi", "Nimbus Works", "HR Executive", "Node.js / NestJS Developer"),
]

SUBJECT_TEMPLATE = "{{my_name}} — {{role_hint}} at {{company_name}}"
BODY_TEMPLATE = """Hi {{contact_name}},

I'm {{my_name}}, a {{my_experience}} engineer working mainly with {{my_skills}}.

I'm reaching out about {{role_hint}} openings at {{company_name}}. My resume is
attached — happy to share more detail on anything relevant.

Thanks for your time,
{{my_name}}"""

SIGNATURE = "Demo User\nexample.com"

# (contact index, outcome, days ago it was sent)
PLAN = [
    (0, "replied", 9),
    (1, "awaiting", 9),
    (2, "replied", 8),
    (3, "bounced", 8),
    (4, "awaiting", 7),
    (5, "awaiting", 7),
    (6, "failed", 6),
    (7, "queued", None),
]

REPLIES = {
    0: (
        "priya.sharma@acmesystems.example",
        "Thanks for reaching out. Your Kafka and NestJS background looks relevant to a role "
        "we're opening next month — could you share your notice period and expected CTC?",
    ),
    2: (
        "rahul.m@zenithtech.example",
        "Appreciate the note. We're not hiring at staff level right now, but I've kept your "
        "profile and will come back when the platform team expands in Q4.",
    ),
}

BOUNCE_REASON = (
    "Diagnostic-Code: smtp; 550-5.1.1 The email account that you tried to reach does not exist. "
    "Please try double-checking the recipient's email address for typos."
)

FAILURE_REASON = "SMTP rejected the login. For Gmail you need a 16-character App Password with 2-Step Verification on."

FOLLOWUP_SUBJECT = "Re: {{original_subject}}"
FOLLOWUP_BODY = """Hi {{contact_name}},

Just floating this back to the top of your inbox in case it got buried. Still
very interested in {{role_hint}} at {{company_name}}, and happy to work around
whatever your hiring timeline looks like.

Thanks again,
{{my_name}}"""


def render(template: str, context: dict) -> str:
    text = template
    for key, value in context.items():
        text = text.replace("{{" + key + "}}", str(value or ""))
    if text.lower().startswith("hi ,"):
        text = "Hi there," + text[4:]
    return text.replace("Hi ,", "Hi there,")


async def get_user(email: str, session) -> UserDB:
    user = (await session.execute(select(UserDB).where(UserDB.email == email))).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"No user with email {email}. Run scripts/seed_profiles.py first.")
    return user


async def purge(user_id: int, session) -> None:
    campaigns = (
        await session.execute(
            select(OutreachCampaignDB.id).where(
                OutreachCampaignDB.user_id == user_id,
                OutreachCampaignDB.name.like(f"{DEMO_TAG}%"),
            )
        )
    ).scalars().all()

    if campaigns:
        await session.execute(delete(OutreachMessageDB).where(OutreachMessageDB.campaign_id.in_(campaigns)))
        await session.execute(delete(OutreachCampaignDB).where(OutreachCampaignDB.id.in_(campaigns)))

    demo_emails = [c[0] for c in CONTACTS]
    await session.execute(
        delete(OutreachMessageDB).where(
            OutreachMessageDB.user_id == user_id, OutreachMessageDB.to_email.in_(demo_emails)
        )
    )
    await session.execute(
        delete(OutreachContactDB).where(
            OutreachContactDB.user_id == user_id, OutreachContactDB.email.in_(demo_emails)
        )
    )

    account = (
        await session.execute(select(UserEmailAccountDB).where(UserEmailAccountDB.user_id == user_id))
    ).scalar_one_or_none()
    if account is not None and account.smtp_password_encrypted:
        from app.services.outreach.crypto import decrypt_secret

        if decrypt_secret(account.smtp_password_encrypted) == PLACEHOLDER_PASSWORD:
            await session.delete(account)
            print("  removed the demo sending account (placeholder password)")
        else:
            print("  kept your sending account — its password is not the placeholder")

    print(f"  removed {len(campaigns)} demo campaign(s) and up to {len(demo_emails)} demo contacts")


async def seed(user: UserDB, session) -> None:
    now = datetime.utcnow()

    account = (
        await session.execute(select(UserEmailAccountDB).where(UserEmailAccountDB.user_id == user.id))
    ).scalar_one_or_none()
    if account is None:
        account = UserEmailAccountDB(
            user_id=user.id,
            from_name="Demo User",
            from_email=user.email,
            smtp_username=user.email,
            smtp_password_encrypted=encrypt_secret(PLACEHOLDER_PASSWORD),
            signature=SIGNATURE,
            daily_send_cap=25,
            send_interval_seconds=45,
            is_verified=False,
            last_synced_at=now - timedelta(hours=3),
        )
        session.add(account)
        print("  created a sending account with a PLACEHOLDER password (replace it before sending)")
    else:
        print("  left your existing sending account alone")

    contacts: list[OutreachContactDB] = []
    for email_address, name, company, title, role_hint in CONTACTS:
        contact = (
            await session.execute(
                select(OutreachContactDB).where(
                    OutreachContactDB.user_id == user.id, OutreachContactDB.email == email_address
                )
            )
        ).scalar_one_or_none()
        if contact is None:
            contact = OutreachContactDB(
                user_id=user.id,
                email=email_address,
                contact_name=name,
                company_name=company,
                title=title,
                role_hint=role_hint,
                source="csv",
            )
            session.add(contact)
        contacts.append(contact)

    await session.flush()

    campaign = OutreachCampaignDB(
        user_id=user.id,
        name=DEMO_CAMPAIGN_NAME,
        subject_template=SUBJECT_TEMPLATE,
        body_template=BODY_TEMPLATE,
        # Paused, not running: nothing is actually draining this, and a campaign
        # that claims to be running while nothing moves is a lie in the UI.
        status="paused",
        attach_resume=True,
        personalize_with_llm=False,
        followup_enabled=True,
        followup_after_days=4,
        started_at=now - timedelta(days=9),
    )
    session.add(campaign)
    await session.flush()

    base_context = {
        "my_name": account.from_name,
        "my_experience": "6.5-year",
        "my_skills": "node.js, python, postgresql, nestjs",
    }

    originals: dict[int, OutreachMessageDB] = {}

    for index, outcome, days_ago in PLAN:
        contact = contacts[index]
        context = {
            **base_context,
            "contact_name": contact.contact_name,
            "company_name": contact.company_name,
            "role_hint": contact.role_hint,
        }
        sent_at = now - timedelta(days=days_ago) if days_ago is not None else None
        body = render(BODY_TEMPLATE, context) + "\n\n" + SIGNATURE

        message = OutreachMessageDB(
            user_id=user.id,
            campaign_id=campaign.id,
            contact_id=contact.id,
            to_email=contact.email,
            to_name=contact.contact_name,
            company_name=contact.company_name,
            subject=render(SUBJECT_TEMPLATE, context),
            body=body,
            attached_resume=True,
            step=1,
            status="queued" if outcome == "queued" else ("failed" if outcome == "failed" else "sent"),
            sent_at=sent_at,
            message_id=f"<demo-{campaign.id}-{index}@jobradar.local>" if sent_at else None,
        )

        if outcome == "replied":
            reply_from, snippet = REPLIES[index]
            message.replied_at = sent_at + timedelta(days=1, hours=4)
            message.reply_from = reply_from
            message.reply_snippet = snippet
        elif outcome == "bounced":
            message.bounced_at = sent_at + timedelta(minutes=2)
            message.bounce_reason = BOUNCE_REASON
        elif outcome == "failed":
            message.error = FAILURE_REASON
            message.sent_at = None
            message.message_id = None

        session.add(message)
        originals[index] = message

    await session.flush()

    # Follow-ups: only for the awaiting ones whose 4 days have elapsed. One
    # already went out, one is still queued — which is what the sequence looks
    # like mid-flight.
    followup_plan = [(1, "sent", 4), (4, "queued", None)]
    for index, status, days_ago in followup_plan:
        parent = originals[index]
        contact = contacts[index]
        context = {
            **base_context,
            "contact_name": contact.contact_name,
            "company_name": contact.company_name,
            "role_hint": contact.role_hint,
            "original_subject": parent.subject,
        }
        sent_at = now - timedelta(days=days_ago) if days_ago is not None else None

        session.add(OutreachMessageDB(
            user_id=user.id,
            campaign_id=campaign.id,
            contact_id=contact.id,
            parent_id=parent.id,
            step=2,
            to_email=contact.email,
            to_name=contact.contact_name,
            company_name=contact.company_name,
            subject=render(FOLLOWUP_SUBJECT, context),
            body=render(FOLLOWUP_BODY, context) + "\n\n" + SIGNATURE,
            attached_resume=False,
            status=status,
            sent_at=sent_at,
            scheduled_for=now,
            message_id=f"<demo-{campaign.id}-{index}-f2@jobradar.local>" if sent_at else None,
        ))

    await session.flush()
    print(f"  created campaign '{DEMO_CAMPAIGN_NAME}' with {len(PLAN)} initial + {len(followup_plan)} follow-up emails")
    print("  outcomes: 2 replied · 3 awaiting · 1 bounced · 1 failed · 1 queued")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=DEFAULT_EMAIL, help=f"user to seed (default: {DEFAULT_EMAIL})")
    parser.add_argument("--purge", action="store_true", help="remove seeded demo data instead of creating it")
    args = parser.parse_args()

    await db.connect()
    async with db.get_session() as session:
        user = await get_user(args.email, session)

        if args.purge:
            print(f"Purging demo outreach data for {args.email}:")
            await purge(user.id, session)
        else:
            print(f"Seeding demo outreach data for {args.email}:")
            await purge(user.id, session)   # re-runnable: clear the previous seed first
            await seed(user, session)

        await session.commit()

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
