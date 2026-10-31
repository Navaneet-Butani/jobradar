"""Outreach business logic — sending identity, contacts, campaigns, single sends.

Two send paths share one log (`outreach_messages`) and one daily cap:
  - `send_from_application` — one email about a job already being tracked
  - campaigns — a batch over selected contacts, drained by `runner.py`
"""

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import NotFoundError, ValidationError
from ...models import (
    ApplicationDB,
    CompanyDB,
    JobDB,
    JobProfileDB,
    OutreachCampaignDB,
    OutreachContactDB,
    OutreachMessageDB,
    UserEmailAccountDB,
    UserResumeDB,
)
from ...services.outreach.crypto import encrypt_secret
from ...services.outreach.csv_import import parse_contacts_csv
from ...services.outreach.feedback import (
    queue_due_followups,
    sync_feedback as pull_mailbox_feedback,
)
from ...services.outreach.quota import previously_emailed, remaining_today, next_window_hint, sent_today
from ...services.outreach.sender import OutreachSendError, send_as_user, verify_account
from ...services.outreach import templates as tpl

logger = logging.getLogger(__name__)


class OutreachService:

    # ---------------- sending identity ----------------

    async def get_account(self, user_id: int, session: AsyncSession) -> Optional[UserEmailAccountDB]:
        result = await session.execute(
            select(UserEmailAccountDB).where(UserEmailAccountDB.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def require_account(self, user_id: int, session: AsyncSession) -> UserEmailAccountDB:
        account = await self.get_account(user_id, session)
        if account is None:
            raise ValidationError(
                "No sending account configured. Add your Gmail address and a 16-character "
                "App Password under Outreach → Sending account first."
            )
        return account

    async def upsert_account(self, user_id: int, data, session: AsyncSession) -> UserEmailAccountDB:
        account = await self.get_account(user_id, session)
        if account is None:
            account = UserEmailAccountDB(user_id=user_id)
            session.add(account)

        account.from_name = data.from_name
        account.from_email = str(data.from_email)
        account.smtp_username = str(data.smtp_username)
        # Gmail shows app passwords in groups of four; users paste the spaces along with it.
        account.smtp_password_encrypted = encrypt_secret(data.smtp_password.replace(" ", ""))
        account.smtp_host = data.smtp_host
        account.smtp_port = data.smtp_port
        account.daily_send_cap = data.daily_send_cap
        account.send_interval_seconds = data.send_interval_seconds
        account.signature = data.signature
        account.is_verified = False
        account.last_verified_at = None

        await session.flush()
        await session.refresh(account)
        return account

    async def verify_account(self, user_id: int, session: AsyncSession) -> UserEmailAccountDB:
        account = await self.require_account(user_id, session)
        await verify_account(account)   # raises OutreachSendError
        account.is_verified = True
        account.last_verified_at = datetime.utcnow()
        await session.flush()
        await session.refresh(account)
        return account

    async def delete_account(self, user_id: int, session: AsyncSession) -> None:
        account = await self.get_account(user_id, session)
        if account is None:
            raise NotFoundError("No sending account configured")
        await session.delete(account)

    async def sync_feedback(self, user_id: int, session: AsyncSession) -> dict:
        """Refresh replies/bounces from the mailbox, then queue any follow-ups now due."""
        await self.require_account(user_id, session)

        sync = await pull_mailbox_feedback(user_id, session)
        if sync.get("error"):
            return {**sync, "followups_queued": 0, "skipped_replied": 0, "skipped_bounced": 0}

        followups = await queue_due_followups(user_id, session)
        return {
            **sync,
            "followups_queued": followups["queued"],
            "skipped_replied": followups["skipped_replied"],
            "skipped_bounced": followups["skipped_bounced"],
        }

    async def account_payload(self, account: UserEmailAccountDB, session: AsyncSession) -> dict:
        used = await sent_today(account.user_id, session)
        return {
            "id": account.id,
            "last_synced_at": account.last_synced_at,
            "last_sync_error": account.last_sync_error,
            "from_name": account.from_name,
            "from_email": account.from_email,
            "smtp_host": account.smtp_host,
            "smtp_port": account.smtp_port,
            "smtp_username": account.smtp_username,
            "daily_send_cap": account.daily_send_cap,
            "send_interval_seconds": account.send_interval_seconds,
            "signature": account.signature,
            "is_verified": account.is_verified,
            "last_verified_at": account.last_verified_at,
            "sent_today": used,
            "remaining_today": max(0, account.daily_send_cap - used),
        }

    # ---------------- contacts ----------------

    async def list_contacts(self, user_id: int, session: AsyncSession) -> tuple[List[dict], int]:
        contacts = (
            await session.execute(
                select(OutreachContactDB)
                .where(OutreachContactDB.user_id == user_id)
                .order_by(OutreachContactDB.company_name, OutreachContactDB.id)
            )
        ).scalars().all()

        history = await previously_emailed(user_id, [c.email for c in contacts], session)
        payload = [self._contact_payload(c, history) for c in contacts]
        return payload, len(payload)

    def _contact_payload(self, contact: OutreachContactDB, history: dict) -> dict:
        return {
            "id": contact.id,
            "email": contact.email,
            "contact_name": contact.contact_name,
            "company_name": contact.company_name,
            "title": contact.title,
            "role_hint": contact.role_hint,
            "notes": contact.notes,
            "source": contact.source,
            "last_emailed_at": history.get(contact.email),
            "created_at": contact.created_at,
            "updated_at": contact.updated_at,
        }

    async def _get_owned_contact(self, user_id: int, contact_id: int, session: AsyncSession) -> OutreachContactDB:
        contact = (
            await session.execute(
                select(OutreachContactDB).where(
                    OutreachContactDB.id == contact_id, OutreachContactDB.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if contact is None:
            raise NotFoundError("Contact not found")
        return contact

    async def create_contact(self, user_id: int, data, session: AsyncSession) -> OutreachContactDB:
        email = str(data.email).lower()
        existing = (
            await session.execute(
                select(OutreachContactDB).where(
                    OutreachContactDB.user_id == user_id, OutreachContactDB.email == email
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ValidationError(f"{email} is already in your contacts")

        contact = OutreachContactDB(
            user_id=user_id,
            email=email,
            contact_name=data.contact_name,
            company_name=data.company_name,
            title=data.title,
            role_hint=data.role_hint,
            notes=data.notes,
            source="manual",
        )
        session.add(contact)
        await session.flush()
        await session.refresh(contact)
        return contact

    async def update_contact(self, user_id: int, contact_id: int, data, session: AsyncSession) -> OutreachContactDB:
        contact = await self._get_owned_contact(user_id, contact_id, session)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(contact, field, str(value).lower() if field == "email" and value else value)
        await session.flush()
        await session.refresh(contact)
        return contact

    async def delete_contact(self, user_id: int, contact_id: int, session: AsyncSession) -> None:
        contact = await self._get_owned_contact(user_id, contact_id, session)
        await session.delete(contact)

    async def import_contacts_csv(self, user_id: int, data: bytes, session: AsyncSession) -> dict:
        rows, problems = parse_contacts_csv(data)
        if not rows:
            return {"imported": 0, "updated": 0, "skipped": 0, "problems": problems, "contacts": []}

        existing = {
            c.email: c
            for c in (
                await session.execute(
                    select(OutreachContactDB).where(
                        OutreachContactDB.user_id == user_id,
                        OutreachContactDB.email.in_([r["email"] for r in rows]),
                    )
                )
            ).scalars().all()
        }

        imported = updated = 0
        touched: list[OutreachContactDB] = []

        for row in rows:
            contact = existing.get(row["email"])
            if contact is None:
                contact = OutreachContactDB(user_id=user_id, email=row["email"], source="csv")
                session.add(contact)
                imported += 1
            else:
                updated += 1
            # A blank cell in the CSV shouldn't wipe a value already on file.
            for field in ("contact_name", "company_name", "title", "role_hint", "notes"):
                if row.get(field):
                    setattr(contact, field, row[field])
            touched.append(contact)

        await session.flush()
        for contact in touched:
            await session.refresh(contact)

        history = await previously_emailed(user_id, [c.email for c in touched], session)
        return {
            "imported": imported,
            "updated": updated,
            "skipped": len(problems),
            "problems": problems,
            "contacts": [self._contact_payload(c, history) for c in touched],
        }

    # ---------------- shared rendering ----------------

    async def _merge_context(
        self, user_id: int, account: UserEmailAccountDB, contact: OutreachContactDB, session: AsyncSession
    ) -> dict:
        profile = (
            await session.execute(
                select(JobProfileDB)
                .where(JobProfileDB.user_id == user_id, JobProfileDB.is_active.is_(True))
                .order_by(JobProfileDB.id)
                .limit(1)
            )
        ).scalar_one_or_none()

        return tpl.build_context(
            contact_name=contact.contact_name,
            company_name=contact.company_name,
            title=contact.title,
            role_hint=contact.role_hint,
            my_name=account.from_name,
            years_exp=profile.years_exp if profile else None,
            skills=(profile.must_have_skills + profile.nice_to_have_skills) if profile else None,
        )

    def _with_signature(self, body: str, account: UserEmailAccountDB) -> str:
        if not account.signature:
            return body
        return f"{body.rstrip()}\n\n{account.signature.strip()}"

    async def _selected_contacts(
        self, user_id: int, contact_ids: List[int], session: AsyncSession
    ) -> List[OutreachContactDB]:
        if not contact_ids:
            raise ValidationError("Select at least one contact")
        contacts = (
            await session.execute(
                select(OutreachContactDB).where(
                    OutreachContactDB.user_id == user_id, OutreachContactDB.id.in_(contact_ids)
                ).order_by(OutreachContactDB.id)
            )
        ).scalars().all()
        if not contacts:
            raise NotFoundError("None of the selected contacts were found")
        return list(contacts)

    async def _has_resume_file(self, user_id: int, session: AsyncSession) -> tuple[bool, Optional[str]]:
        resume = (
            await session.execute(select(UserResumeDB).where(UserResumeDB.user_id == user_id))
        ).scalar_one_or_none()
        if resume is None:
            return False, None
        return bool(resume.file_data), resume.filename

    # ---------------- campaigns ----------------

    async def preview(self, user_id: int, data, session: AsyncSession) -> dict:
        account = await self.require_account(user_id, session)
        contacts = await self._selected_contacts(user_id, data.contact_ids, session)
        history = await previously_emailed(user_id, [c.email for c in contacts], session)

        warnings: list[str] = []
        unknown = tpl.unknown_fields(data.subject_template) | tpl.unknown_fields(data.body_template)
        if unknown:
            warnings.append(
                f"Unknown merge field(s) {', '.join(sorted(unknown))} will render empty. "
                f"Available: {', '.join(tpl.MERGE_FIELDS)}."
            )

        has_file, filename = await self._has_resume_file(user_id, session)
        if data.attach_resume and not has_file:
            warnings.append(
                "Attachment is on but no resume file is stored — re-upload your resume on the "
                "Profile page, or these will send without it."
            )

        repeats = [c.email for c in contacts if c.email in history]
        if repeats:
            warnings.append(
                f"{len(repeats)} of these you've emailed before. Not blocked — you turned the "
                "lifetime per-contact limit off — but check the list before sending."
            )

        missing_company = sum(1 for c in contacts if not c.company_name)
        if missing_company:
            warnings.append(f"{missing_company} contact(s) have no company name; those emails will read generically.")

        items = []
        for contact in contacts[: data.limit]:
            context = await self._merge_context(user_id, account, contact, session)
            items.append({
                "contact_id": contact.id,
                "to_email": contact.email,
                "to_name": contact.contact_name,
                "company_name": contact.company_name,
                "subject": tpl.render(data.subject_template, context),
                "body": self._with_signature(tpl.render(data.body_template, context), account),
                "previously_emailed_at": history.get(contact.email),
            })

        remaining = await remaining_today(user_id, account.daily_send_cap, session)
        return {
            "items": items,
            "total_selected": len(contacts),
            "remaining_today": remaining,
            "pacing_note": next_window_hint(remaining, len(contacts)),
            "warnings": warnings,
        }

    async def create_campaign(self, user_id: int, data, session: AsyncSession) -> OutreachCampaignDB:
        account = await self.require_account(user_id, session)
        contacts = await self._selected_contacts(user_id, data.contact_ids, session)

        campaign = OutreachCampaignDB(
            user_id=user_id,
            name=data.name,
            subject_template=data.subject_template,
            body_template=data.body_template,
            attach_resume=data.attach_resume,
            personalize_with_llm=data.personalize_with_llm,
            followup_enabled=data.followup_enabled,
            followup_after_days=data.followup_after_days,
            followup_subject_template=data.followup_subject_template,
            followup_body_template=data.followup_body_template,
            status="draft",
        )
        session.add(campaign)
        await session.flush()

        has_file, _ = await self._has_resume_file(user_id, session)
        attach = data.attach_resume and has_file

        for contact in contacts:
            context = await self._merge_context(user_id, account, contact, session)
            body = tpl.render(data.body_template, context)

            if data.personalize_with_llm:
                rewritten = await tpl.personalize(body, contact.company_name, contact.role_hint)
                if rewritten:
                    body = rewritten

            session.add(OutreachMessageDB(
                user_id=user_id,
                campaign_id=campaign.id,
                contact_id=contact.id,
                to_email=contact.email,
                to_name=contact.contact_name,
                company_name=contact.company_name,
                subject=tpl.render(data.subject_template, context),
                body=self._with_signature(body, account),
                attached_resume=attach,
                status="queued",
            ))

        await session.flush()
        await session.refresh(campaign)
        return campaign

    async def update_campaign(self, user_id: int, campaign_id: int, data, session: AsyncSession) -> OutreachCampaignDB:
        campaign = await self.get_owned_campaign(user_id, campaign_id, session)
        if campaign.status == "running":
            raise ValidationError("Pause the campaign before editing it")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(campaign, field, value)
        await session.flush()
        await session.refresh(campaign)
        return campaign

    async def get_owned_campaign(self, user_id: int, campaign_id: int, session: AsyncSession) -> OutreachCampaignDB:
        campaign = (
            await session.execute(
                select(OutreachCampaignDB).where(
                    OutreachCampaignDB.id == campaign_id, OutreachCampaignDB.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if campaign is None:
            raise NotFoundError("Campaign not found")
        return campaign

    async def _campaign_counts(self, campaign_id: int, session: AsyncSession) -> dict:
        rows = (
            await session.execute(
                select(OutreachMessageDB.status, func.count())
                .where(OutreachMessageDB.campaign_id == campaign_id)
                .group_by(OutreachMessageDB.status)
            )
        ).all()
        counts = {"queued": 0, "sent": 0, "failed": 0, "skipped": 0, "cancelled": 0}
        for status, count in rows:
            counts[status] = count
        counts["total"] = sum(counts.values())

        feedback = (
            await session.execute(
                select(
                    func.count(OutreachMessageDB.replied_at),
                    func.count(OutreachMessageDB.bounced_at),
                    func.count().filter(OutreachMessageDB.step == 2),
                ).where(OutreachMessageDB.campaign_id == campaign_id)
            )
        ).one()
        counts["replied"], counts["bounced"], counts["followups"] = feedback
        # Anything sent that neither answered nor bounced is still in the air.
        counts["awaiting"] = max(0, counts["sent"] - counts["replied"] - counts["bounced"])
        return counts

    async def campaign_payload(
        self, campaign: OutreachCampaignDB, session: AsyncSession, include_messages: bool = False
    ) -> dict:
        payload = {
            "id": campaign.id,
            "name": campaign.name,
            "subject_template": campaign.subject_template,
            "body_template": campaign.body_template,
            "status": campaign.status,
            "attach_resume": campaign.attach_resume,
            "personalize_with_llm": campaign.personalize_with_llm,
            "followup_enabled": campaign.followup_enabled,
            "followup_after_days": campaign.followup_after_days,
            "followup_subject_template": campaign.followup_subject_template,
            "followup_body_template": campaign.followup_body_template,
            "started_at": campaign.started_at,
            "completed_at": campaign.completed_at,
            "created_at": campaign.created_at,
            "counts": await self._campaign_counts(campaign.id, session),
            "messages": [],
        }

        if include_messages:
            messages = (
                await session.execute(
                    select(OutreachMessageDB)
                    .where(OutreachMessageDB.campaign_id == campaign.id)
                    .order_by(OutreachMessageDB.id)
                )
            ).scalars().all()
            payload["messages"] = [
                {
                    "id": m.id,
                    "to_email": m.to_email,
                    "to_name": m.to_name,
                    "company_name": m.company_name,
                    "subject": m.subject,
                    "body": m.body,
                    "attached_resume": m.attached_resume,
                    "status": m.status,
                    "error": m.error,
                    "sent_at": m.sent_at,
                    "step": m.step,
                    "replied_at": m.replied_at,
                    "reply_from": m.reply_from,
                    "reply_snippet": m.reply_snippet,
                    "bounced_at": m.bounced_at,
                    "bounce_reason": m.bounce_reason,
                }
                for m in messages
            ]

        return payload

    async def list_campaigns(self, user_id: int, session: AsyncSession) -> tuple[List[dict], int]:
        campaigns = (
            await session.execute(
                select(OutreachCampaignDB)
                .where(OutreachCampaignDB.user_id == user_id)
                .order_by(OutreachCampaignDB.id.desc())
            )
        ).scalars().all()
        # Messages are included here so the list's "Recipients" expander has
        # something to show without a second round trip. Fine at this scale —
        # a handful of users, campaigns of tens, not thousands.
        payload = [await self.campaign_payload(c, session, include_messages=True) for c in campaigns]
        return payload, len(payload)

    async def mark_running(self, user_id: int, campaign_id: int, session: AsyncSession) -> dict:
        """Flip to running and report what will actually go out today."""
        account = await self.require_account(user_id, session)
        campaign = await self.get_owned_campaign(user_id, campaign_id, session)

        counts = await self._campaign_counts(campaign.id, session)
        if counts["queued"] == 0:
            raise ValidationError("Nothing left queued in this campaign")

        campaign.status = "running"
        if campaign.started_at is None:
            campaign.started_at = datetime.utcnow()
        await session.flush()

        remaining = await remaining_today(user_id, account.daily_send_cap, session)
        return {
            "campaign_id": campaign.id,
            "queued": counts["queued"],
            "remaining_today": remaining,
            "pacing_note": next_window_hint(remaining, counts["queued"]),
        }

    async def pause_campaign(self, user_id: int, campaign_id: int, session: AsyncSession) -> OutreachCampaignDB:
        campaign = await self.get_owned_campaign(user_id, campaign_id, session)
        # The drain loop re-reads status between sends, so this stops it after
        # the in-flight message rather than mid-SMTP-conversation.
        campaign.status = "paused"
        await session.flush()
        await session.refresh(campaign)
        return campaign

    async def delete_campaign(self, user_id: int, campaign_id: int, session: AsyncSession) -> None:
        campaign = await self.get_owned_campaign(user_id, campaign_id, session)
        await session.delete(campaign)

    # ---------------- application-side single send ----------------

    async def _application_context(self, user_id: int, application_id: int, session: AsyncSession):
        row = (
            await session.execute(
                select(ApplicationDB, JobDB, CompanyDB)
                .join(JobDB, JobDB.id == ApplicationDB.job_id)
                .outerjoin(CompanyDB, CompanyDB.id == JobDB.company_id)
                .where(ApplicationDB.id == application_id, ApplicationDB.user_id == user_id)
            )
        ).first()
        if row is None:
            raise NotFoundError("Application not found")
        return row

    async def draft_for_application(self, user_id: int, application_id: int, session: AsyncSession) -> dict:
        account = await self.require_account(user_id, session)
        application, job, company = await self._application_context(user_id, application_id, session)

        profile = (
            await session.execute(
                select(JobProfileDB)
                .where(JobProfileDB.user_id == user_id, JobProfileDB.is_active.is_(True))
                .order_by(JobProfileDB.id)
                .limit(1)
            )
        ).scalar_one_or_none()

        company_name = company.name if company else None
        context = tpl.build_context(
            contact_name=application.contact_name,
            company_name=company_name,
            title=None,
            role_hint=job.title,
            my_name=account.from_name,
            years_exp=profile.years_exp if profile else None,
            skills=(profile.must_have_skills + profile.nice_to_have_skills) if profile else None,
        )

        subject = f"Following up — {job.title} application"
        body = tpl.render(
            "Hi {{contact_name}},\n\n"
            "I applied for the {{role_hint}} role at {{company_name}} and wanted to follow up "
            "directly. I'm a {{my_experience}} engineer working mainly with {{my_skills}}.\n\n"
            "My resume is attached. Happy to share anything else that would help.\n\n"
            "Thanks for your time,\n{{my_name}}",
            context,
        )

        history = await previously_emailed(user_id, [application.contact_email] if application.contact_email else [], session)
        warnings: list[str] = []

        has_file, _ = await self._has_resume_file(user_id, session)
        if not has_file:
            warnings.append("No resume file stored — re-upload it on the Profile page to attach it.")
        if not application.contact_email:
            warnings.append("No contact email on this application yet — add one before sending.")

        return {
            "subject": subject,
            "body": self._with_signature(body, account),
            "to_email": application.contact_email,
            "to_name": application.contact_name,
            "company_name": company_name,
            "job_title": job.title,
            "previously_emailed_at": history.get((application.contact_email or "").lower()),
            "remaining_today": await remaining_today(user_id, account.daily_send_cap, session),
            "warnings": warnings,
        }

    async def send_from_application(self, user_id: int, data, session: AsyncSession) -> dict:
        account = await self.require_account(user_id, session)
        application, job, company = await self._application_context(user_id, data.application_id, session)

        remaining = await remaining_today(user_id, account.daily_send_cap, session)
        if remaining <= 0:
            raise ValidationError(
                f"Daily cap of {account.daily_send_cap} reached. Raise it in Outreach settings "
                "or send tomorrow."
            )

        to_email = str(data.to_email).lower()
        attachment = None
        if data.attach_resume:
            resume = (
                await session.execute(select(UserResumeDB).where(UserResumeDB.user_id == user_id))
            ).scalar_one_or_none()
            if resume is not None and resume.file_data:
                attachment = (resume.filename, resume.file_data)

        message = OutreachMessageDB(
            user_id=user_id,
            application_id=application.id,
            to_email=to_email,
            to_name=data.to_name,
            company_name=company.name if company else None,
            subject=data.subject,
            body=data.body,
            attached_resume=attachment is not None,
            status="queued",
        )
        session.add(message)
        await session.flush()

        try:
            sent_message_id = await send_as_user(
                account=account,
                to_email=to_email,
                to_name=data.to_name,
                subject=data.subject,
                body=data.body,
                attachment=attachment,
            )
            message.status = "sent"
            message.sent_at = datetime.utcnow()
            message.message_id = sent_message_id
        except OutreachSendError as e:
            message.status = "failed"
            message.error = str(e)[:1000]
            await session.flush()
            raise ValidationError(str(e))

        # Keep the tracker honest: the contact we actually used, and a timeline note.
        application.contact_email = to_email
        if data.to_name:
            application.contact_name = data.to_name
        application.timeline = (application.timeline or []) + [{
            "at": datetime.utcnow().isoformat(),
            "from_status": application.status,
            "to_status": application.status,
            "note": f"Outreach email sent to {to_email}",
        }]

        if data.save_contact:
            await self._upsert_contact_from_send(
                user_id, to_email, data.to_name, company.name if company else None, job.title, session
            )

        await session.flush()
        return {
            "message_id": message.id,
            "to_email": to_email,
            "status": message.status,
            "sent_at": message.sent_at,
            "remaining_today": await remaining_today(user_id, account.daily_send_cap, session),
        }

    async def _upsert_contact_from_send(
        self,
        user_id: int,
        email: str,
        name: Optional[str],
        company_name: Optional[str],
        role_hint: Optional[str],
        session: AsyncSession,
    ) -> None:
        existing = (
            await session.execute(
                select(OutreachContactDB).where(
                    OutreachContactDB.user_id == user_id, OutreachContactDB.email == email
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(OutreachContactDB(
                user_id=user_id,
                email=email,
                contact_name=name,
                company_name=company_name,
                role_hint=role_hint,
                source="discovered",
            ))
            return

        existing.contact_name = existing.contact_name or name
        existing.company_name = existing.company_name or company_name
