"""Repository for application data access operations."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import select, func, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from .base import BaseRepository, CacheableRepositoryMixin
from ..models import ApplicationDB, JobDB, CompanyDB
from ..models.user import ApplicationCreate, ApplicationUpdate, ApplicationResponse, ApplicationStats

logger = logging.getLogger(__name__)


class ApplicationRepository(CacheableRepositoryMixin, BaseRepository[ApplicationDB]):
    """Repository for application data access."""

    def __init__(self):
        super().__init__(ApplicationDB, cache_ttl=300)  # 5-minute cache

    @staticmethod
    def _to_app_data(app: ApplicationDB, job: JobDB, company: Optional[CompanyDB]) -> Dict[str, Any]:
        return {
            'id': app.id,
            'job_id': job.id,
            'job_profile_id': app.job_profile_id,
            'job_title': job.title,
            'company_name': company.name if company else 'Unknown',
            'status': app.status,
            'applied_date': app.applied_date,
            'application_method': app.application_method,
            'resume_version': app.resume_version,
            'cover_letter': app.cover_letter,
            'referral_name': app.referral_name,
            'contact_name': app.contact_name,
            'contact_email': app.contact_email,
            'notes': app.notes,
            'next_step': app.next_step,
            'next_step_date': app.next_step_date,
            'timeline': app.timeline or [],
            'response_received': app.response_received,
            'response_date': app.response_date,
            'interview_scheduled': app.interview_scheduled,
            'created_at': app.created_at,
            'updated_at': app.updated_at
        }

    async def create_application(
        self,
        user_id: int,
        application_data: ApplicationCreate,
        session: AsyncSession = None
    ) -> ApplicationDB:
        """Create new application tracking record."""
        # Check if application already exists
        existing = await self.find_by_user_and_job(user_id, application_data.job_id, session)
        if existing:
            raise ValueError("Application already exists for this job")

        app_dict = application_data.model_dump(exclude_unset=True)
        app_dict['user_id'] = user_id

        try:
            application = ApplicationDB(**app_dict)
            session.add(application)
            await session.flush()

            # Invalidate user's application cache
            await self._invalidate_cache(f"user:{user_id}:applications:*")

            return application
        except Exception as e:
            logger.error(f"Error creating application for user {user_id}, job {application_data.job_id}: {e}")
            raise

    async def find_by_user_and_job(
        self,
        user_id: int,
        job_id: int,
        session: AsyncSession = None
    ) -> Optional[ApplicationDB]:
        """Find application by user and job."""
        try:
            query = select(ApplicationDB).where(
                and_(ApplicationDB.user_id == user_id, ApplicationDB.job_id == job_id)
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding application for user {user_id}, job {job_id}: {e}")
            raise

    async def update_application(
        self,
        user_id: int,
        application_id: int,
        update_data: ApplicationUpdate,
        session: AsyncSession = None
    ) -> Optional[ApplicationDB]:
        """Update application with validation."""
        try:
            # Get existing application
            application = await self.get_by_id(application_id, session)
            if not application or application.user_id != user_id:
                return None

            # Update fields
            update_dict = update_data.model_dump(exclude_unset=True, exclude_none=True)

            new_status = update_dict.get('status')
            if new_status and new_status != application.status:
                # Reassign (not .append) so SQLAlchemy detects the JSONB column as dirty.
                application.timeline = [
                    *(application.timeline or []),
                    {
                        'at': datetime.utcnow().isoformat(),
                        'from_status': application.status,
                        'to_status': new_status,
                        'note': update_dict.get('notes'),
                    },
                ]

            for field, value in update_dict.items():
                if hasattr(application, field):
                    setattr(application, field, value)

            await session.flush()

            # Invalidate cache
            await self._invalidate_cache(f"user:{user_id}:applications:*")

            return application
        except Exception as e:
            logger.error(f"Error updating application {application_id}: {e}")
            raise

    async def get_user_applications(
        self,
        user_id: int,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "applied_date",
        sort_order: str = "desc",
        session: AsyncSession = None
    ) -> List[ApplicationResponse]:
        """Get applications for user with job details."""
        cache_key = self._get_cache_key(
            f"user:{user_id}:applications", status or "all", limit, offset, sort_by, sort_order
        )

        # Try cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return [ApplicationResponse(**app) for app in cached_result]

        try:
            query = (
                select(ApplicationDB, JobDB, CompanyDB)
                .join(JobDB, ApplicationDB.job_id == JobDB.id)
                .join(CompanyDB, JobDB.company_id == CompanyDB.id, isouter=True)
                .where(ApplicationDB.user_id == user_id)
            )

            if status:
                query = query.where(ApplicationDB.status == status)

            # Apply sorting
            sort_column = getattr(ApplicationDB, sort_by, ApplicationDB.applied_date)
            if sort_order == "desc":
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(asc(sort_column))

            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            applications = []

            for app, job, company in result.all():
                applications.append(ApplicationResponse(**self._to_app_data(app, job, company)))

            # Cache result
            cache_data = [app.model_dump() for app in applications]
            await self._set_cache(cache_key, cache_data, ttl=300)

            return applications
        except Exception as e:
            logger.error(f"Error getting applications for user {user_id}: {e}")
            raise

    async def get_applications_count(
        self,
        user_id: int,
        status: Optional[str] = None,
        session: AsyncSession = None
    ) -> int:
        """Get count of user applications."""
        try:
            query = select(func.count(ApplicationDB.id)).where(ApplicationDB.user_id == user_id)

            if status:
                query = query.where(ApplicationDB.status == status)

            result = await session.execute(query)
            return result.scalar_one()
        except Exception as e:
            logger.error(f"Error counting applications for user {user_id}: {e}")
            raise

    async def calculate_application_stats(
        self,
        user_id: int,
        session: AsyncSession = None
    ) -> ApplicationStats:
        """Calculate comprehensive application statistics."""
        cache_key = self._get_cache_key(f"user:{user_id}:app_stats")

        # Try cache first
        cached_stats = await self._get_from_cache(cache_key)
        if cached_stats:
            return ApplicationStats(**cached_stats)

        try:
            # Total applications
            total_query = select(func.count(ApplicationDB.id)).where(ApplicationDB.user_id == user_id)
            total_result = await session.execute(total_query)
            total_applications = total_result.scalar_one()

            if total_applications == 0:
                empty_stats = ApplicationStats(
                    total_applications=0,
                    applications_by_status={},
                    applications_by_method={},
                    response_rate=0.0,
                    interview_rate=0.0,
                    offer_rate=0.0,
                    applications_this_week=0,
                    applications_this_month=0,
                    top_companies=[]
                )
                await self._set_cache(cache_key, empty_stats.model_dump(), ttl=600)
                return empty_stats

            # Applications by status
            status_query = (
                select(ApplicationDB.status, func.count(ApplicationDB.id))
                .where(ApplicationDB.user_id == user_id)
                .group_by(ApplicationDB.status)
            )
            status_result = await session.execute(status_query)
            applications_by_status = {status: count for status, count in status_result.all()}

            # Applications by method
            method_query = (
                select(ApplicationDB.application_method, func.count(ApplicationDB.id))
                .where(ApplicationDB.user_id == user_id)
                .group_by(ApplicationDB.application_method)
            )
            method_result = await session.execute(method_query)
            applications_by_method = {method: count for method, count in method_result.all()}

            # Response rate
            responses_query = select(func.count(ApplicationDB.id)).where(
                and_(ApplicationDB.user_id == user_id, ApplicationDB.response_received == True)
            )
            responses_result = await session.execute(responses_query)
            responses_count = responses_result.scalar_one()
            response_rate = (responses_count / total_applications) * 100

            # Interview rate
            interviews_query = select(func.count(ApplicationDB.id)).where(
                and_(ApplicationDB.user_id == user_id, ApplicationDB.interview_scheduled == True)
            )
            interviews_result = await session.execute(interviews_query)
            interviews_count = interviews_result.scalar_one()
            interview_rate = (interviews_count / total_applications) * 100

            # Offer rate
            offers_count = applications_by_status.get('offer', 0)
            offer_rate = (offers_count / total_applications) * 100

            # Recent applications
            week_ago = datetime.utcnow() - timedelta(days=7)
            month_ago = datetime.utcnow() - timedelta(days=30)

            week_query = select(func.count(ApplicationDB.id)).where(
                and_(ApplicationDB.user_id == user_id, ApplicationDB.applied_date >= week_ago)
            )
            week_result = await session.execute(week_query)
            applications_this_week = week_result.scalar_one()

            month_query = select(func.count(ApplicationDB.id)).where(
                and_(ApplicationDB.user_id == user_id, ApplicationDB.applied_date >= month_ago)
            )
            month_result = await session.execute(month_query)
            applications_this_month = month_result.scalar_one()

            # Top companies
            companies_query = (
                select(CompanyDB.name, func.count(ApplicationDB.id).label('count'))
                .join(JobDB, ApplicationDB.job_id == JobDB.id)
                .join(CompanyDB, JobDB.company_id == CompanyDB.id)
                .where(ApplicationDB.user_id == user_id)
                .group_by(CompanyDB.name)
                .order_by(desc('count'))
                .limit(5)
            )
            companies_result = await session.execute(companies_query)
            top_companies = [
                {'company': name, 'applications': count}
                for name, count in companies_result.all()
            ]

            # Average response time
            avg_response_query = (
                select(func.avg(
                    func.extract('epoch', ApplicationDB.response_date - ApplicationDB.applied_date) / 86400
                ))
                .where(
                    and_(
                        ApplicationDB.user_id == user_id,
                        ApplicationDB.response_received == True,
                        ApplicationDB.response_date.isnot(None)
                    )
                )
            )
            avg_response_result = await session.execute(avg_response_query)
            avg_response_time_days = avg_response_result.scalar_one()

            stats = ApplicationStats(
                total_applications=total_applications,
                applications_by_status=applications_by_status,
                applications_by_method=applications_by_method,
                response_rate=round(response_rate, 2),
                interview_rate=round(interview_rate, 2),
                offer_rate=round(offer_rate, 2),
                avg_response_time_days=round(avg_response_time_days, 1) if avg_response_time_days else None,
                applications_this_week=applications_this_week,
                applications_this_month=applications_this_month,
                top_companies=top_companies
            )

            # Cache for 10 minutes
            await self._set_cache(cache_key, stats.model_dump(), ttl=600)

            return stats
        except Exception as e:
            logger.error(f"Error calculating application stats for user {user_id}: {e}")
            raise

    async def get_applications_needing_follow_up(
        self,
        user_id: int,
        days_threshold: int = 7,
        session: AsyncSession = None
    ) -> List[ApplicationResponse]:
        """Get applications that need follow-up based on next_step_date."""
        try:
            threshold_date = datetime.utcnow() - timedelta(days=days_threshold)

            query = (
                select(ApplicationDB, JobDB, CompanyDB)
                .join(JobDB, ApplicationDB.job_id == JobDB.id)
                .join(CompanyDB, JobDB.company_id == CompanyDB.id, isouter=True)
                .where(
                    and_(
                        ApplicationDB.user_id == user_id,
                        ApplicationDB.next_step_date.isnot(None),
                        ApplicationDB.next_step_date <= threshold_date,
                        ApplicationDB.status.in_(['applied', 'screening', 'interview'])
                    )
                )
                .order_by(asc(ApplicationDB.next_step_date))
            )

            result = await session.execute(query)
            applications = []

            for app, job, company in result.all():
                applications.append(ApplicationResponse(**self._to_app_data(app, job, company)))

            return applications
        except Exception as e:
            logger.error(f"Error getting follow-up applications for user {user_id}: {e}")
            raise

    async def get_due_today(
        self,
        user_id: int,
        session: AsyncSession = None
    ) -> List[ApplicationResponse]:
        """Applications whose next_step is due today or earlier — still open (not rejected/ghosted)."""
        try:
            end_of_today = datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)

            query = (
                select(ApplicationDB, JobDB, CompanyDB)
                .join(JobDB, ApplicationDB.job_id == JobDB.id)
                .join(CompanyDB, JobDB.company_id == CompanyDB.id, isouter=True)
                .where(
                    and_(
                        ApplicationDB.user_id == user_id,
                        ApplicationDB.next_step_date.isnot(None),
                        ApplicationDB.next_step_date <= end_of_today,
                        ApplicationDB.status.notin_(['rejected', 'ghosted']),
                    )
                )
                .order_by(asc(ApplicationDB.next_step_date))
            )

            result = await session.execute(query)
            return [
                ApplicationResponse(**self._to_app_data(app, job, company))
                for app, job, company in result.all()
            ]
        except Exception as e:
            logger.error(f"Error getting due-today applications for user {user_id}: {e}")
            raise

    async def auto_ghost_stale(
        self,
        user_id: int,
        session: AsyncSession = None,
        days_threshold: int = 21,
    ) -> int:
        """Flip 'applied' applications with no movement in `days_threshold` days to 'ghosted'."""
        threshold_date = datetime.utcnow() - timedelta(days=days_threshold)

        result = await session.execute(
            select(ApplicationDB).where(
                and_(
                    ApplicationDB.user_id == user_id,
                    ApplicationDB.status == 'applied',
                    ApplicationDB.applied_date <= threshold_date,
                )
            )
        )
        stale = result.scalars().all()
        for app in stale:
            app.timeline = [
                *(app.timeline or []),
                {
                    'at': datetime.utcnow().isoformat(),
                    'from_status': 'applied',
                    'to_status': 'ghosted',
                    'note': f'Auto-ghosted after {days_threshold} days of silence',
                },
            ]
            app.status = 'ghosted'

        if stale:
            await session.flush()
        return len(stale)

    async def nudge_stale_screening(
        self,
        user_id: int,
        session: AsyncSession = None,
        days_threshold: int = 10,
    ) -> int:
        """Phase 3 Task 2.1: surface 'screening' applications that have gone quiet.

        Sets a next step so they appear in "Due today" rather than sitting in
        the Screening column indefinitely. Screening is where applications go to
        die silently — a recruiter said "we'll be in touch" and then didn't.

        Only fills an *empty* next step: a date the user set by hand always wins.
        """
        threshold_date = datetime.utcnow() - timedelta(days=days_threshold)

        result = await session.execute(
            select(ApplicationDB).where(
                and_(
                    ApplicationDB.user_id == user_id,
                    ApplicationDB.status == 'screening',
                    ApplicationDB.updated_at <= threshold_date,
                    ApplicationDB.next_step_date.is_(None),
                )
            )
        )
        stale = result.scalars().all()
        now = datetime.utcnow()

        for app in stale:
            days_quiet = max(days_threshold, (now - app.updated_at).days)
            app.next_step = f"Check in — no movement in {days_quiet} days"
            app.next_step_date = now
            app.timeline = [
                *(app.timeline or []),
                {
                    'at': now.isoformat(),
                    'from_status': 'screening',
                    'to_status': 'screening',
                    'note': f'Flagged for a check-in after {days_quiet} days in screening',
                },
            ]

        if stale:
            await session.flush()
        return len(stale)

    async def delete_application(
        self,
        user_id: int,
        application_id: int,
        session: AsyncSession = None
    ) -> bool:
        """Delete application if it belongs to user."""
        try:
            application = await self.get_by_id(application_id, session)
            if not application or application.user_id != user_id:
                return False

            await self.delete(application_id, session)

            # Invalidate cache
            await self._invalidate_cache(f"user:{user_id}:applications:*")

            return True
        except Exception as e:
            logger.error(f"Error deleting application {application_id}: {e}")
            raise

    async def get_applications_by_status_timeline(
        self,
        user_id: int,
        session: AsyncSession = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get applications grouped by month for timeline view."""
        try:
            query = (
                select(
                    func.extract('year', ApplicationDB.applied_date).label('year'),
                    func.extract('month', ApplicationDB.applied_date).label('month'),
                    ApplicationDB.status,
                    func.count(ApplicationDB.id).label('count')
                )
                .where(ApplicationDB.user_id == user_id)
                .group_by('year', 'month', ApplicationDB.status)
                .order_by('year', 'month')
            )

            result = await session.execute(query)
            timeline_data = {}

            for year, month, status, count in result.all():
                month_key = f"{int(year)}-{int(month):02d}"
                if month_key not in timeline_data:
                    timeline_data[month_key] = []

                timeline_data[month_key].append({
                    'status': status,
                    'count': count
                })

            return timeline_data
        except Exception as e:
            logger.error(f"Error getting timeline data for user {user_id}: {e}")
            raise