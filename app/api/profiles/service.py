"""Profiles business logic — job_profiles are always scoped to their owning user."""

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import NotFoundError
from ...models import JobProfileDB
from .schema import JobProfileCreateRequest, JobProfileUpdateRequest

logger = logging.getLogger(__name__)


class ProfilesService:
    async def list_profiles(self, user_id: int, session: AsyncSession) -> List[JobProfileDB]:
        result = await session.execute(
            select(JobProfileDB).where(JobProfileDB.user_id == user_id).order_by(JobProfileDB.id)
        )
        return list(result.scalars().all())

    async def get_owned_profile(self, user_id: int, profile_id: int, session: AsyncSession) -> JobProfileDB:
        result = await session.execute(
            select(JobProfileDB).where(
                JobProfileDB.id == profile_id, JobProfileDB.user_id == user_id
            )
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            raise NotFoundError("Profile not found")
        return profile

    async def create_profile(
        self, user_id: int, data: JobProfileCreateRequest, session: AsyncSession
    ) -> JobProfileDB:
        profile = JobProfileDB(user_id=user_id, **data.model_dump())
        session.add(profile)
        await session.flush()
        await session.refresh(profile)
        return profile

    async def update_profile(
        self, user_id: int, profile_id: int, data: JobProfileUpdateRequest, session: AsyncSession
    ) -> JobProfileDB:
        profile = await self.get_owned_profile(user_id, profile_id, session)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
        await session.flush()
        await session.refresh(profile)
        return profile

    async def delete_profile(self, user_id: int, profile_id: int, session: AsyncSession) -> None:
        profile = await self.get_owned_profile(user_id, profile_id, session)
        await session.delete(profile)
