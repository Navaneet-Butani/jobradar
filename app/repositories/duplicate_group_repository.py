"""Repository for duplicate groups management."""

from typing import List, Optional, Dict, Any
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload

from ..core.database import db
from ..models import DuplicateGroupDB, DuplicateMappingDB, JobDB


class DuplicateGroupRepository:
    """Repository for managing duplicate groups and mappings."""

    def __init__(self, database_manager=None):
        self.db = database_manager or db

    async def create_group(self, group_data: Dict[str, Any]) -> Optional[int]:
        """Create a new duplicate group."""
        async with self.db.get_session() as session:
            try:
                group = DuplicateGroupDB(**group_data)
                session.add(group)
                await session.commit()
                await session.refresh(group)
                return group.id
            except Exception as e:
                await session.rollback()
                raise e

    async def get_group(self, group_id: int) -> Optional[DuplicateGroupDB]:
        """Get group by ID."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(DuplicateGroupDB).where(DuplicateGroupDB.id == group_id)
            )
            return result.scalar_one_or_none()

    async def update_group(self, group_id: int, updates: Dict[str, Any]) -> bool:
        """Update group fields."""
        async with self.db.get_session() as session:
            try:
                result = await session.execute(
                    update(DuplicateGroupDB)
                    .where(DuplicateGroupDB.id == group_id)
                    .values(**updates)
                )
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                raise e

    async def delete_group(self, group_id: int) -> bool:
        """Delete a group."""
        async with self.db.get_session() as session:
            try:
                result = await session.execute(
                    delete(DuplicateGroupDB).where(DuplicateGroupDB.id == group_id)
                )
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                raise e

    async def create_mapping(self, mapping_data: Dict[str, Any]) -> Optional[int]:
        """Create a new job-group mapping."""
        async with self.db.get_session() as session:
            try:
                mapping = DuplicateMappingDB(**mapping_data)
                session.add(mapping)
                await session.commit()
                await session.refresh(mapping)
                return mapping.id
            except Exception as e:
                await session.rollback()
                raise e

    async def get_job_mapping(self, job_id: int) -> Optional[DuplicateMappingDB]:
        """Get mapping for a job."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(DuplicateMappingDB).where(DuplicateMappingDB.job_id == job_id)
            )
            return result.scalar_one_or_none()

    async def get_group_mappings(self, group_id: int) -> List[DuplicateMappingDB]:
        """Get all mappings for a group."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(DuplicateMappingDB)
                .where(DuplicateMappingDB.group_id == group_id)
                .order_by(DuplicateMappingDB.similarity_score.desc())
            )
            return result.scalars().all()

    async def update_mapping(self, mapping_id: int, updates: Dict[str, Any]) -> bool:
        """Update mapping fields."""
        async with self.db.get_session() as session:
            try:
                result = await session.execute(
                    update(DuplicateMappingDB)
                    .where(DuplicateMappingDB.id == mapping_id)
                    .values(**updates)
                )
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                raise e

    async def delete_mapping(self, mapping_id: int) -> bool:
        """Delete a mapping."""
        async with self.db.get_session() as session:
            try:
                result = await session.execute(
                    delete(DuplicateMappingDB).where(DuplicateMappingDB.id == mapping_id)
                )
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                raise e

    async def delete_group_mappings(self, group_id: int) -> int:
        """Delete all mappings for a group."""
        async with self.db.get_session() as session:
            try:
                result = await session.execute(
                    delete(DuplicateMappingDB).where(DuplicateMappingDB.group_id == group_id)
                )
                await session.commit()
                return result.rowcount
            except Exception as e:
                await session.rollback()
                raise e

    async def get_groups_by_company(self, company_id: int,
                                  exclude_group_id: Optional[int] = None) -> List[DuplicateGroupDB]:
        """Get groups for jobs from a specific company."""
        async with self.db.get_session() as session:
            query = (
                select(DuplicateGroupDB)
                .join(JobDB, DuplicateGroupDB.primary_job_id == JobDB.id)
                .where(JobDB.company_id == company_id)
            )

            if exclude_group_id:
                query = query.where(DuplicateGroupDB.id != exclude_group_id)

            result = await session.execute(query)
            return result.scalars().all()

    async def get_groups_by_hash(self, group_hash: str) -> Optional[DuplicateGroupDB]:
        """Get group by hash."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(DuplicateGroupDB).where(DuplicateGroupDB.group_hash == group_hash)
            )
            return result.scalar_one_or_none()

    async def get_large_groups(self, min_size: int = 10) -> List[DuplicateGroupDB]:
        """Get groups with many members."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(DuplicateGroupDB)
                .where(DuplicateGroupDB.member_count >= min_size)
                .order_by(DuplicateGroupDB.member_count.desc())
            )
            return result.scalars().all()

    async def get_groups_by_quality_range(self, min_quality: float, max_quality: float) -> List[DuplicateGroupDB]:
        """Get groups within quality score range."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(DuplicateGroupDB)
                .where(
                    DuplicateGroupDB.quality_score >= min_quality,
                    DuplicateGroupDB.quality_score <= max_quality
                )
                .order_by(DuplicateGroupDB.quality_score.desc())
            )
            return result.scalars().all()

    async def get_groups_needing_review(self, quality_threshold: float = 0.7) -> List[DuplicateGroupDB]:
        """Get groups with low quality scores that may need review."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(DuplicateGroupDB)
                .where(DuplicateGroupDB.quality_score < quality_threshold)
                .order_by(DuplicateGroupDB.quality_score.asc())
            )
            return result.scalars().all()

    async def get_groups_stats(self) -> Dict[str, Any]:
        """Get statistics about duplicate groups."""
        async with self.db.get_session() as session:
            # Total groups
            total_groups = await session.scalar(select(func.count(DuplicateGroupDB.id)))

            # Average group size
            avg_size = await session.scalar(select(func.avg(DuplicateGroupDB.member_count)))

            # Large groups (>10 members)
            large_groups = await session.scalar(
                select(func.count(DuplicateGroupDB.id))
                .where(DuplicateGroupDB.member_count > 10)
            )

            # Quality distribution
            avg_quality = await session.scalar(select(func.avg(DuplicateGroupDB.quality_score)))
            low_quality_groups = await session.scalar(
                select(func.count(DuplicateGroupDB.id))
                .where(DuplicateGroupDB.quality_score < 0.7)
            )

            # Total jobs in groups
            total_jobs_in_groups = await session.scalar(
                select(func.sum(DuplicateGroupDB.member_count))
            )

            return {
                'total_groups': total_groups or 0,
                'average_size': float(avg_size) if avg_size else 0.0,
                'large_groups': large_groups or 0,
                'average_quality': float(avg_quality) if avg_quality else 0.0,
                'low_quality_groups': low_quality_groups or 0,
                'total_jobs_in_groups': total_jobs_in_groups or 0
            }

    async def get_orphaned_mappings(self) -> List[DuplicateMappingDB]:
        """Get mappings without corresponding groups."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(DuplicateMappingDB)
                .outerjoin(DuplicateGroupDB, DuplicateMappingDB.group_id == DuplicateGroupDB.id)
                .where(DuplicateGroupDB.id.is_(None))
            )
            return result.scalars().all()

    async def cleanup_orphaned_mappings(self) -> int:
        """Clean up mappings without corresponding groups."""
        async with self.db.get_session() as session:
            try:
                # First get orphaned mappings
                orphaned = await self.get_orphaned_mappings()
                orphaned_ids = [m.id for m in orphaned]

                if orphaned_ids:
                    result = await session.execute(
                        delete(DuplicateMappingDB).where(DuplicateMappingDB.id.in_(orphaned_ids))
                    )
                    await session.commit()
                    return result.rowcount

                return 0
            except Exception as e:
                await session.rollback()
                raise e

    async def get_recent_groups(self, days: int = 7) -> List[DuplicateGroupDB]:
        """Get groups created in recent days."""
        from datetime import datetime, timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        async with self.db.get_session() as session:
            result = await session.execute(
                select(DuplicateGroupDB)
                .where(DuplicateGroupDB.created_at >= cutoff_date)
                .order_by(DuplicateGroupDB.created_at.desc())
            )
            return result.scalars().all()