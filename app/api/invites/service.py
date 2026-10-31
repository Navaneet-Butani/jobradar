"""Invite business logic.

Deliberately builds on the tables that already exist rather than adding an
`invites` one: an invite IS a user row that has no password yet, plus a row in
`email_verification_tokens` holding the secret. That keeps "accepting an
invite" and "verifying an email" the same shape, and means no migration.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config.settings import settings
from ...core.exceptions import NotFoundError, ValidationError
from ...core.security import SecurityManager
from ...models import EmailVerificationTokenDB, UserDB, UserProfileDB
from ...services.auth.registration_service import RegistrationService
from ...services.auth.session_service import DeviceInfo, SessionService
from ...services.auth.token_service import TokenService
from ...services.email import get_email_service
from .schema import MemberResponse

logger = logging.getLogger(__name__)

# Long enough to survive a weekend and a "what's this link?" phone call, short
# enough that a leaked link stops working.
INVITE_TTL_DAYS = 7


class InvitesService:
    # ------------------------------------------------------------------ read

    @staticmethod
    def invite_url(token: str) -> str:
        return f"{settings.frontend_url.rstrip('/')}/invite/{token}"

    @staticmethod
    async def list_members(session: AsyncSession, caller: UserDB) -> List[MemberResponse]:
        rows = (
            await session.execute(
                select(UserDB, UserProfileDB)
                .outerjoin(UserProfileDB, UserProfileDB.user_id == UserDB.id)
                .order_by(UserDB.id)
            )
        ).all()

        tokens = {
            row.user_id: row
            for row in (
                await session.execute(
                    select(EmailVerificationTokenDB)
                    .where(EmailVerificationTokenDB.is_verified.is_(False))
                    .order_by(EmailVerificationTokenDB.created_at)
                )
            ).scalars()
        }

        now = datetime.utcnow()
        members: List[MemberResponse] = []
        for user, profile in rows:
            # No password has ever been set, so the invite was never claimed.
            pending = user.password_hash is None
            token = tokens.get(user.id) if pending else None
            members.append(
                MemberResponse(
                    id=user.id,
                    email=user.email,
                    first_name=profile.first_name if profile else None,
                    last_name=profile.last_name if profile else None,
                    is_active=user.is_active,
                    is_admin=user.is_admin,
                    is_self=user.id == caller.id,
                    pending=pending,
                    invite_url=InvitesService.invite_url(token.token) if token else None,
                    invite_expires_at=token.expires_at if token else None,
                    invite_expired=bool(token and token.expires_at < now),
                    last_login_at=user.last_login_at,
                    created_at=user.created_at,
                )
            )
        return members

    @staticmethod
    async def _load_token(token: str, session: AsyncSession) -> EmailVerificationTokenDB:
        row = (
            await session.execute(
                select(EmailVerificationTokenDB).where(EmailVerificationTokenDB.token == token)
            )
        ).scalar_one_or_none()
        if row is None or row.is_verified:
            raise NotFoundError("This invite link is not valid")
        if row.expires_at < datetime.utcnow():
            raise ValidationError("This invite link has expired - ask for a new one")
        return row

    @staticmethod
    async def preview(token: str, session: AsyncSession) -> dict:
        """Public: what the accept page shows before anyone is authenticated.

        Returns the invitee's own email and nothing about the rest of the
        deployment, because the caller holds nothing but the link.
        """
        row = await InvitesService._load_token(token, session)
        user = await session.get(UserDB, row.user_id)
        if user is None or user.password_hash is not None:
            raise NotFoundError("This invite has already been used")

        profile = (
            await session.execute(select(UserProfileDB).where(UserProfileDB.user_id == user.id))
        ).scalar_one_or_none()

        # Outer join, not inner: the seeded admin account predates the profile
        # table being populated, and an inner join there silently returned
        # nothing, so the accept page said "You've been invited" with no name.
        inviter = (
            await session.execute(
                select(UserProfileDB.first_name, UserDB.email)
                .select_from(UserDB)
                .outerjoin(UserProfileDB, UserProfileDB.user_id == UserDB.id)
                .where(UserDB.is_admin.is_(True))
                .limit(1)
            )
        ).first()

        return {
            "email": user.email,
            "first_name": profile.first_name if profile else None,
            "last_name": profile.last_name if profile else None,
            "invited_by": (inviter[0] or inviter[1]) if inviter else None,
        }

    # ----------------------------------------------------------------- write

    @staticmethod
    async def create_invite(
        email: str,
        first_name: Optional[str],
        last_name: Optional[str],
        session: AsyncSession,
        caller: UserDB,
    ) -> Tuple[MemberResponse, bool, Optional[str]]:
        email = email.lower().strip()

        existing = (
            await session.execute(select(UserDB).where(UserDB.email == email))
        ).scalar_one_or_none()

        if existing is not None and existing.password_hash is not None:
            raise ValidationError(f"{email} already has an account")

        if existing is not None:
            # Re-inviting someone who never accepted: keep the row and mint a
            # fresh token. Anything else leaves an orphaned half-user behind
            # every time a link expires.
            user = existing
            await session.execute(
                delete(EmailVerificationTokenDB).where(EmailVerificationTokenDB.user_id == user.id)
            )
        else:
            user = UserDB(
                email=email,
                password_hash=None,  # set when the invite is accepted
                is_active=False,     # and cannot log in until then
                email_verified=False,
            )
            session.add(user)
            await session.flush()
            session.add(UserProfileDB(user_id=user.id, first_name=first_name, last_name=last_name))

        if first_name or last_name:
            profile = (
                await session.execute(select(UserProfileDB).where(UserProfileDB.user_id == user.id))
            ).scalar_one_or_none()
            if profile is not None:
                profile.first_name = first_name
                profile.last_name = last_name

        token = SecurityManager.generate_api_key()
        session.add(
            EmailVerificationTokenDB(
                user_id=user.id,
                email=user.email,
                token=token,
                expires_at=datetime.utcnow() + timedelta(days=INVITE_TTL_DAYS),
            )
        )
        await session.flush()

        emailed, error = await InvitesService._send_invite_email(
            user.email, first_name, InvitesService.invite_url(token), caller
        )

        members = await InvitesService.list_members(session, caller)
        member = next(m for m in members if m.id == user.id)
        return member, emailed, error

    @staticmethod
    async def _send_invite_email(
        to_email: str, first_name: Optional[str], link: str, caller: UserDB
    ) -> Tuple[bool, Optional[str]]:
        """Best effort. The link is shown in the UI regardless, because the free
        Resend tier only delivers to the account owner's own address."""
        try:
            service = get_email_service()
            if not service.is_email_configured():
                return False, "Email is not configured - copy the link instead"
            sent = await service.send_direct_email(
                to_email=to_email,
                subject=f"You have been invited to {settings.ses_from_name}",
                template_name="invite",
                template_data={
                    "user_name": first_name or to_email.split("@")[0],
                    "recipient_email": to_email,
                    "invited_by": caller.email,
                    "invite_link": link,
                    "expires_days": INVITE_TTL_DAYS,
                },
            )
            return bool(sent), None if sent else "The mail provider rejected the send"
        except Exception as e:  # never fail an invite because mail is down
            logger.warning(f"Invite email to {to_email} failed: {e}")
            return False, str(e)

    @staticmethod
    async def accept(
        token: str,
        password: str,
        first_name: Optional[str],
        last_name: Optional[str],
        device_info: DeviceInfo,
        session: AsyncSession,
    ) -> dict:
        row = await InvitesService._load_token(token, session)
        user = await session.get(UserDB, row.user_id)
        if user is None or user.password_hash is not None:
            raise NotFoundError("This invite has already been used")

        # Same rules the normal signup enforces - an invite is not a reason to
        # accept a weaker password.
        validation = RegistrationService.validate_password(password)
        if not validation["is_valid"]:
            raise ValidationError("; ".join(validation["errors"]))

        user.password_hash = SecurityManager.hash_password(password)
        user.is_active = True
        # The link itself was the proof of address; it only ever reached this
        # mailbox. Demanding a second round trip would lock the account out,
        # because get_current_verified_user rejects unverified users.
        user.email_verified = True

        profile = (
            await session.execute(select(UserProfileDB).where(UserProfileDB.user_id == user.id))
        ).scalar_one_or_none()
        if profile is None:
            profile = UserProfileDB(user_id=user.id)
            session.add(profile)
        if first_name:
            profile.first_name = first_name.strip()
        if last_name:
            profile.last_name = last_name.strip()

        row.is_verified = True
        row.verified_at = datetime.utcnow()
        await session.flush()

        tokens = await TokenService.create_token_pair(user.id)
        refresh_token, refresh_expires = TokenService.create_refresh_token(user.id)
        session_id = await SessionService.create_session(
            user_id=user.id,
            device_info=device_info,
            refresh_token=refresh_token,
            refresh_token_expires=refresh_expires,
            session=session,
        )

        return {"user": user, "tokens": tokens, "session_id": session_id}

    @staticmethod
    async def revoke(user_id: int, session: AsyncSession, caller: UserDB) -> None:
        """Withdraw an invite that was never accepted. Refuses to touch a real
        account - deleting one would take its matches and applications with it."""
        if user_id == caller.id:
            raise ValidationError("You cannot revoke your own account")

        # Columns, not the entity, and a Core DELETE rather than
        # session.delete(): UserDB.profile is a relationship with no delete
        # cascade, so the ORM tried to null out user_profiles.user_id -- which
        # is that table's primary key -- and the flush died with
        # "Dependency rule ... tried to blank-out primary key column".
        # The FKs are already ON DELETE CASCADE, so the database handles it.
        row = (
            await session.execute(
                select(UserDB.id, UserDB.password_hash).where(UserDB.id == user_id)
            )
        ).first()
        if row is None:
            raise NotFoundError("Account not found")
        if row.password_hash is not None:
            raise ValidationError(
                "That invite has already been accepted - deactivate the account instead"
            )

        await session.execute(delete(UserDB).where(UserDB.id == user_id))

    @staticmethod
    async def set_active(
        user_id: int, is_active: bool, session: AsyncSession, caller: UserDB
    ) -> MemberResponse:
        user = await session.get(UserDB, user_id)
        if user is None:
            raise NotFoundError("Account not found")
        if user.id == caller.id:
            raise ValidationError("You cannot deactivate your own account")
        if user.is_admin and not is_active:
            raise ValidationError("Admin accounts cannot be deactivated")

        user.is_active = is_active
        await session.flush()

        members = await InvitesService.list_members(session, caller)
        return next(m for m in members if m.id == user_id)
