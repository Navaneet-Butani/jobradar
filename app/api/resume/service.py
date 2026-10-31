"""Resume business logic — one master resume per user, replaced on re-upload."""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import NotFoundError
from ...models import UserResumeDB
from ...services.resume_extract import extract_resume_text

logger = logging.getLogger(__name__)


class ResumeService:
    async def get_resume(self, user_id: int, session: AsyncSession) -> Optional[UserResumeDB]:
        result = await session.execute(select(UserResumeDB).where(UserResumeDB.user_id == user_id))
        return result.scalar_one_or_none()

    async def upsert_resume(
        self, user_id: int, filename: str, content_type: Optional[str], data: bytes, session: AsyncSession
    ) -> UserResumeDB:
        """Extract text and store it, replacing any resume the user already had."""
        text = extract_resume_text(filename, data)

        resume = await self.get_resume(user_id, session)
        if resume is None:
            resume = UserResumeDB(user_id=user_id)
            session.add(resume)

        resume.filename = filename
        resume.content_type = content_type
        resume.content_text = text
        resume.char_count = len(text)
        # Original bytes kept so outreach emails can attach the real file.
        resume.file_data = data
        resume.file_size = len(data)

        await session.flush()
        await session.refresh(resume)
        logger.info(f"Stored resume for user {user_id}: {filename} ({len(text)} chars)")
        return resume

    async def delete_resume(self, user_id: int, session: AsyncSession) -> None:
        resume = await self.get_resume(user_id, session)
        if resume is None:
            raise NotFoundError("No resume on file")
        await session.delete(resume)
