"""Packet business logic — profile ownership check, then delegate to the builder."""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import NotFoundError
from ...models import JobProfileDB
from ...services.packet import build_packet

logger = logging.getLogger(__name__)


class PacketService:
    async def generate(
        self, user_id: int, job_id: int, profile_id: int, session: AsyncSession
    ) -> Optional[dict]:
        result = await session.execute(
            select(JobProfileDB).where(
                JobProfileDB.id == profile_id, JobProfileDB.user_id == user_id
            )
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            raise NotFoundError("Profile not found")

        return await build_packet(user_id, job_id, profile, session)
