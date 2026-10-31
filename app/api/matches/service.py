"""Matches business logic — the ranked feed, state transitions, and stats."""

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import NotFoundError, ValidationError
from ...models import CompanyDB, JobDB, JobDetailDB, JobProfileDB, JobSourceDB, MatchDB
from ...api.applications.service import ApplicationsService
from .schema import MATCH_STATES, MatchJobResponse

logger = logging.getLogger(__name__)



class MatchesService:
    def __init__(self):
        self.applications_service = ApplicationsService()

    async def _assert_owns_profile(self, user_id: int, profile_id: int, session: AsyncSession) -> None:
        result = await session.execute(
            select(JobProfileDB.id).where(
                JobProfileDB.id == profile_id, JobProfileDB.user_id == user_id
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundError("Profile not found")

    def _row_to_response(
        self,
        match: MatchDB,
        job: JobDB,
        company: Optional[CompanyDB],
        source_name: Optional[str],
        description_length: Optional[int] = None,
    ) -> MatchJobResponse:
        return MatchJobResponse(
            job_id=job.id,
            title=job.title,
            company_name=company.name if company else None,
            company_id=company.id if company else None,
            company_logo_url=company.logo_url if company else None,
            company_rating=float(company.rating) if company and company.rating is not None else None,
            company_rating_count=company.rating_count if company else None,
            city=job.city,
            is_remote=job.is_remote,
            remote_scope=job.remote_scope,
            min_exp_years=job.min_exp_years,
            max_exp_years=job.max_exp_years,
            salary_min=float(job.salary_min) if job.salary_min is not None else None,
            salary_max=float(job.salary_max) if job.salary_max is not None else None,
            salary_currency=job.salary_currency,
            salary_period=job.salary_period,
            salary_disclosed=job.salary_disclosed,
            posted_date=job.posted_date,
            apply_url=job.apply_url,
            source_name=source_name,
            poster_name=job.poster_name,
            poster_title=job.poster_title,
            source_applicant_count=job.source_applicant_count,
            # Instahyre publishes no description at all and Hirist only fills in
            # after a detail fetch, so the card says up front whether opening the
            # job will show anything to read.
            has_description=bool(description_length and description_length > 50),
            score=float(match.score),
            reasons=match.reasons or {},
            explanation=match.explanation,
            state=match.state,
            surfaced_at=match.surfaced_at,
        )

    async def get_feed(
        self,
        user_id: int,
        profile_id: int,
        session: AsyncSession,
        state: Optional[str] = None,
        min_score: Optional[float] = None,
        remote_only: bool = False,
        my_cities_only: bool = False,
        sort: str = "score",
        page: int = 1,
        limit: int = 20,
    ):
        await self._assert_owns_profile(user_id, profile_id, session)

        query = (
            select(MatchDB, JobDB, CompanyDB, JobSourceDB.name, func.length(JobDetailDB.description))
            .join(JobDB, JobDB.id == MatchDB.job_id)
            .outerjoin(CompanyDB, CompanyDB.id == JobDB.company_id)
            .outerjoin(JobSourceDB, JobSourceDB.id == JobDB.source_id)
            .outerjoin(JobDetailDB, JobDetailDB.job_id == JobDB.id)
            .where(MatchDB.job_profile_id == profile_id, JobDB.status == "active")
        )
        count_query = (
            select(func.count())
            .select_from(MatchDB)
            .join(JobDB, JobDB.id == MatchDB.job_id)
            .where(MatchDB.job_profile_id == profile_id, JobDB.status == "active")
        )

        if state:
            query = query.where(MatchDB.state == state)
            count_query = count_query.where(MatchDB.state == state)
        else:
            # Dismissing a job is the user saying "not this one" -- leaving it in
            # the default feed made the button do nothing visible, so the only
            # way to act on it was to keep scrolling past it forever. It is still
            # reachable through the Dismissed filter, which is why this hides
            # rather than deletes.
            query = query.where(MatchDB.state != "dismissed")
            count_query = count_query.where(MatchDB.state != "dismissed")
        if min_score is not None:
            query = query.where(MatchDB.score >= min_score)
            count_query = count_query.where(MatchDB.score >= min_score)
        if remote_only:
            query = query.where(JobDB.is_remote.is_(True))
            count_query = count_query.where(JobDB.is_remote.is_(True))
        if my_cities_only:
            # The profile's own onsite cities -- "jobs I could commute to".
            cities = (await session.execute(
                select(JobProfileDB.cities).where(JobProfileDB.id == profile_id)
            )).scalar_one() or []
            lowered = [c.lower() for c in cities]
            query = query.where(func.lower(JobDB.city).in_(lowered))
            count_query = count_query.where(func.lower(JobDB.city).in_(lowered))

        total_count = (await session.execute(count_query)).scalar_one()

        # Score first is right for "what should I look at", but a feed checked
        # daily also needs "what arrived since yesterday" -- at 679 matches the
        # newest posting can sit 300 rows down a score-ordered list.
        if sort == "newest":
            order = (JobDB.posted_date.desc().nullslast(), MatchDB.surfaced_at.desc())
        else:
            order = (MatchDB.score.desc(),)
        query = query.order_by(*order).limit(limit).offset((page - 1) * limit)
        rows = (await session.execute(query)).all()

        matches = [
            self._row_to_response(m, j, company, source_name, description_length)
            for m, j, company, source_name, description_length in rows
        ]
        return matches, total_count

    async def get_states(
        self, user_id: int, profile_id: int, job_ids: List[int], session: AsyncSession
    ) -> dict:
        """job_id -> state, for the ids given.

        Search runs against the whole corpus and knows nothing about the feed,
        so a job already marked Applied looked identical to an unseen one. This
        is the cheap way to close that gap: the search page asks about the 20
        ids it is rendering rather than the jobs pipeline growing a per-user
        join it needs for nothing else.
        """
        if not job_ids:
            return {}
        await self._assert_owns_profile(user_id, profile_id, session)

        rows = (
            await session.execute(
                select(MatchDB.job_id, MatchDB.state).where(
                    MatchDB.job_profile_id == profile_id, MatchDB.job_id.in_(job_ids)
                )
            )
        ).all()
        return {job_id: state for job_id, state in rows}

    async def get_single(
        self, user_id: int, profile_id: int, job_id: int, session: AsyncSession
    ) -> Optional[MatchJobResponse]:
        await self._assert_owns_profile(user_id, profile_id, session)

        query = (
            select(MatchDB, JobDB, CompanyDB, JobSourceDB.name, func.length(JobDetailDB.description))
            .join(JobDB, JobDB.id == MatchDB.job_id)
            .outerjoin(CompanyDB, CompanyDB.id == JobDB.company_id)
            .outerjoin(JobSourceDB, JobSourceDB.id == JobDB.source_id)
            .outerjoin(JobDetailDB, JobDetailDB.job_id == JobDB.id)
            .where(MatchDB.job_profile_id == profile_id, MatchDB.job_id == job_id)
        )
        row = (await session.execute(query)).first()
        if row is None:
            return None

        match, job, company, source_name, description_length = row
        return self._row_to_response(match, job, company, source_name, description_length)

    async def update_state(
        self, user_id: int, profile_id: int, job_id: int, new_state: str, session: AsyncSession
    ) -> MatchDB:
        if new_state not in MATCH_STATES:
            raise ValidationError(f"Invalid state '{new_state}'")
        await self._assert_owns_profile(user_id, profile_id, session)

        result = await session.execute(
            select(MatchDB).where(MatchDB.job_profile_id == profile_id, MatchDB.job_id == job_id)
        )
        match = result.scalar_one_or_none()
        if match is None:
            # Search runs over the whole corpus, so it surfaces jobs this profile
            # was never scored against -- flagging one there has to work, or the
            # button is decoration. Score 0 is honest ("nobody scored this"), and
            # the next matching pass fills in a real one: engine.py's upsert
            # updates score while leaving state alone.
            job_exists = await session.scalar(select(JobDB.id).where(JobDB.id == job_id))
            if job_exists is None:
                raise NotFoundError("Job not found")
            match = MatchDB(
                job_profile_id=profile_id,
                job_id=job_id,
                score=0,
                reasons={},
                explanation=None,
                state="new",
            )
            session.add(match)

        match.state = new_state
        match.state_changed_at = datetime.utcnow()

        if new_state == "applied":
            # Get-or-create — hitting [Applied] twice is a no-op, not an error.
            await self.applications_service.create_from_match(
                user_id=user_id, job_id=job_id, job_profile_id=profile_id, session=session
            )

        await session.flush()
        await session.refresh(match)
        return match

    async def get_stats(self, user_id: int, profile_id: int, session: AsyncSession) -> dict:
        await self._assert_owns_profile(user_id, profile_id, session)

        result = await session.execute(
            select(MatchDB.state, func.count())
            .join(JobDB, JobDB.id == MatchDB.job_id)
            .where(MatchDB.job_profile_id == profile_id, JobDB.status == "active")
            .group_by(MatchDB.state)
        )
        by_state = {state: 0 for state in MATCH_STATES}
        for state, count in result.all():
            by_state[state] = count

        today_result = await session.execute(
            select(func.count())
            .select_from(MatchDB)
            .join(JobDB, JobDB.id == MatchDB.job_id)
            .where(
                MatchDB.job_profile_id == profile_id,
                JobDB.status == "active",
                MatchDB.state == "new",
                func.date(MatchDB.surfaced_at) == func.current_date(),
            )
        )
        new_today = today_result.scalar_one()

        return {
            "profile_id": profile_id,
            "by_state": by_state,
            "new_today": new_today,
            "total": sum(by_state.values()),
        }
