"""Application tracking business logic service."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...repositories.application_repository import ApplicationRepository
from ...core.exceptions import ValidationError, LimitExceededError, NotFoundError
from ...models.user import ApplicationCreate, ApplicationUpdate, ApplicationResponse, ApplicationStats
from ...models.common import ApplicationStatus, ApplicationMethod
from ...services.followup_draft import generate_followup_draft
from .schema import (
    ApplicationSummaryResponse, ApplicationTimelineResponse,
    FollowUpApplicationsResponse, ApplicationListResponse, DueTodayResponse
)

logger = logging.getLogger(__name__)


class ApplicationsService:
    """Service for application tracking operations."""

    def __init__(self):
        self.repository = ApplicationRepository()

    async def create_application(
        self,
        user_id: int,
        application_data: ApplicationCreate,
        session: AsyncSession = None
    ) -> ApplicationResponse:
        """Create new application tracking record."""
        # Create application using repository
        application_db = await self.repository.create_application(user_id, application_data, session)

        # Get application with job details
        applications = await self.repository.get_user_applications(
            user_id=user_id,
            limit=1,
            offset=0,
            session=session
        )

        if not applications:
            raise ValidationError("Failed to retrieve application details")

        # Find the created application
        for app in applications:
            if app.id == application_db.id:
                return app

        raise ValidationError("Failed to retrieve created application")

    async def update_application(
        self,
        user_id: int,
        application_id: int,
        update_data: ApplicationUpdate,
        session: AsyncSession = None
    ) -> Optional[ApplicationResponse]:
        """Update application with validation."""
        application_db = await self.repository.update_application(
            user_id, application_id, update_data, session
        )

        if not application_db:
            return None

        # Get updated application with job details
        applications = await self.repository.get_user_applications(
            user_id=user_id,
            limit=50,  # Get enough to find the updated application
            session=session
        )

        # Find the updated application
        for app in applications:
            if app.id == application_id:
                return app

        return None

    async def get_user_applications(
        self,
        user_id: int,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "applied_date",
        sort_order: str = "desc",
        session: AsyncSession = None
    ) -> ApplicationListResponse:
        """Get applications for user with pagination."""
        await self.repository.auto_ghost_stale(user_id, session)
        await self.repository.nudge_stale_screening(user_id, session)
        applications = await self.repository.get_user_applications(
            user_id=user_id,
            status=status,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            session=session
        )

        total_count = await self.repository.get_applications_count(
            user_id=user_id,
            status=status,
            session=session
        )

        return ApplicationListResponse(
            applications=applications,
            total_count=total_count,
            limit=limit,
            offset=offset
        )

    async def draft_followup(
        self,
        user_id: int,
        application_id: int,
        session: AsyncSession = None
    ) -> Optional[str]:
        """Generate a follow-up message draft for one application. None if LLM disabled/unavailable."""
        application = await self.get_application_by_id(user_id, application_id, session)
        if not application:
            raise NotFoundError("Application not found")

        return await generate_followup_draft(
            job_title=application.job_title,
            company_name=application.company_name,
            applied_date=application.applied_date,
            timeline=application.timeline,
        )

    async def get_due_today(
        self,
        user_id: int,
        session: AsyncSession = None
    ) -> DueTodayResponse:
        """Applications whose next follow-up is due today or earlier."""
        await self.repository.auto_ghost_stale(user_id, session)
        await self.repository.nudge_stale_screening(user_id, session)
        applications = await self.repository.get_due_today(user_id, session)
        return DueTodayResponse(applications=applications, total_count=len(applications))

    async def create_from_match(
        self,
        user_id: int,
        job_id: int,
        job_profile_id: Optional[int],
        session: AsyncSession = None
    ) -> Optional[ApplicationResponse]:
        """
        Get-or-create the application row behind a match's [Applied] action.
        Returns None (no error) if one already exists — hitting Applied twice
        is not a failure, it's a no-op.
        """
        existing = await self.repository.find_by_user_and_job(user_id, job_id, session)
        if existing:
            return None

        application_data = ApplicationCreate(
            job_id=job_id,
            job_profile_id=job_profile_id,
            status=ApplicationStatus.APPLIED,
            application_method=ApplicationMethod.DIRECT,
            next_step="Follow up",
            next_step_date=datetime.utcnow() + timedelta(days=7),
        )
        return await self.create_application(user_id, application_data, session)

    async def get_application_by_id(
        self,
        user_id: int,
        application_id: int,
        session: AsyncSession = None
    ) -> Optional[ApplicationResponse]:
        """Get specific application by ID."""
        # Get all applications and find the specific one
        applications = await self.repository.get_user_applications(
            user_id=user_id,
            limit=1000,  # Large enough to find any application
            session=session
        )

        for app in applications:
            if app.id == application_id:
                return app

        return None

    async def delete_application(
        self,
        user_id: int,
        application_id: int,
        session: AsyncSession = None
    ) -> bool:
        """Delete application if it belongs to user."""
        return await self.repository.delete_application(user_id, application_id, session)

    async def get_application_stats(
        self,
        user_id: int,
        session: AsyncSession = None
    ) -> ApplicationStats:
        """Get comprehensive application statistics."""
        return await self.repository.calculate_application_stats(user_id, session)

    async def get_applications_needing_follow_up(
        self,
        user_id: int,
        days_threshold: int = 7,
        session: AsyncSession = None
    ) -> FollowUpApplicationsResponse:
        """Get applications that need follow-up."""
        applications = await self.repository.get_applications_needing_follow_up(
            user_id, days_threshold, session
        )

        return FollowUpApplicationsResponse(
            applications=applications,
            total_count=len(applications)
        )

    async def get_application_timeline(
        self,
        user_id: int,
        session: AsyncSession = None
    ) -> ApplicationTimelineResponse:
        """Get applications grouped by month for timeline view."""
        timeline_data = await self.repository.get_applications_by_status_timeline(user_id, session)

        return ApplicationTimelineResponse(
            timeline=timeline_data,
            total_months=len(timeline_data)
        )

    async def get_application_summary(
        self,
        user_id: int,
        session: AsyncSession = None
    ) -> ApplicationSummaryResponse:
        """Get application summary for dashboard."""
        # Get comprehensive stats
        stats = await self.repository.calculate_application_stats(user_id, session)

        # Get follow-up applications
        follow_up_apps = await self.repository.get_applications_needing_follow_up(
            user_id, days_threshold=7, session=session
        )

        # Get recent applications (last 10)
        recent_applications = await self.repository.get_user_applications(
            user_id=user_id,
            limit=10,
            sort_by="applied_date",
            sort_order="desc",
            session=session
        )

        # Count active applications
        active_statuses = ['applied', 'screening', 'interview', 'offer']
        active_count = sum(
            stats.applications_by_status.get(status, 0) for status in active_statuses
        )

        # Convert recent applications to dict format
        recent_apps_data = []
        for app in recent_applications:
            recent_apps_data.append({
                'id': app.id,
                'job_title': app.job_title,
                'company_name': app.company_name,
                'status': app.status,
                'applied_date': app.applied_date,
                'next_step': app.next_step,
                'next_step_date': app.next_step_date
            })

        return ApplicationSummaryResponse(
            total_applications=stats.total_applications,
            active_applications=active_count,
            applications_this_week=stats.applications_this_week,
            applications_this_month=stats.applications_this_month,
            response_rate=stats.response_rate,
            interview_rate=stats.interview_rate,
            offer_rate=stats.offer_rate,
            recent_applications=recent_apps_data,
            follow_up_needed=len(follow_up_apps)
        )

    async def update_application_status(
        self,
        user_id: int,
        application_id: int,
        status: ApplicationStatus,
        notes: Optional[str] = None,
        response_received: Optional[bool] = None,
        response_date: Optional[datetime] = None,
        interview_scheduled: Optional[bool] = None,
        next_step: Optional[str] = None,
        next_step_date: Optional[datetime] = None,
        session: AsyncSession = None
    ) -> Optional[ApplicationResponse]:
        """Update application status with additional fields."""
        update_data = ApplicationUpdate(
            status=status,
            notes=notes,
            response_received=response_received,
            response_date=response_date,
            interview_scheduled=interview_scheduled,
            next_step=next_step,
            next_step_date=next_step_date
        )

        return await self.update_application(user_id, application_id, update_data, session)

    async def update_application_notes(
        self,
        user_id: int,
        application_id: int,
        notes: str,
        session: AsyncSession = None
    ) -> Optional[ApplicationResponse]:
        """Update application notes only."""
        update_data = ApplicationUpdate(notes=notes)
        return await self.update_application(user_id, application_id, update_data, session)

    async def track_application_activity(
        self,
        user_id: int,
        application_id: int,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        session: AsyncSession = None
    ) -> None:
        """Log application activity (the activity table was removed with the analytics features)."""
        logger.info("application %s: %s by user %s %s", application_id, action, user_id, details or {})

    async def get_applications_by_company(
        self,
        user_id: int,
        company_name: str,
        session: AsyncSession = None
    ) -> List[ApplicationResponse]:
        """Get all applications for a specific company."""
        # This would be implemented with a more sophisticated query
        # For now, get all applications and filter
        applications = await self.repository.get_user_applications(
            user_id=user_id,
            limit=1000,
            session=session
        )

        return [app for app in applications if company_name.lower() in app.company_name.lower()]

    async def get_application_insights(
        self,
        user_id: int,
        session: AsyncSession = None
    ) -> Dict[str, Any]:
        """Get application insights and recommendations."""
        stats = await self.repository.calculate_application_stats(user_id, session)

        insights = {
            'total_applications': stats.total_applications,
            'success_metrics': {
                'response_rate': stats.response_rate,
                'interview_rate': stats.interview_rate,
                'offer_rate': stats.offer_rate
            },
            'recommendations': []
        }

        # Generate recommendations based on stats
        if stats.response_rate < 20:
            insights['recommendations'].append({
                'type': 'improve_response_rate',
                'message': 'Your response rate is low. Consider customizing your applications more.',
                'priority': 'high'
            })

        if stats.applications_this_week == 0:
            insights['recommendations'].append({
                'type': 'increase_activity',
                'message': 'No applications this week. Consider increasing your application frequency.',
                'priority': 'medium'
            })

        if stats.avg_response_time_days and stats.avg_response_time_days > 14:
            insights['recommendations'].append({
                'type': 'follow_up',
                'message': 'Average response time is high. Consider following up on pending applications.',
                'priority': 'medium'
            })

        return insights

    async def export_applications(
        self,
        user_id: int,
        format: str = 'csv',
        status_filter: Optional[str] = None,
        session: AsyncSession = None
    ) -> Dict[str, Any]:
        """Export applications data."""
        applications = await self.repository.get_user_applications(
            user_id=user_id,
            status=status_filter,
            limit=1000,  # Max export limit
            session=session
        )

        export_data = []
        for app in applications:
            export_data.append({
                'Job Title': app.job_title,
                'Company': app.company_name,
                'Status': app.status,
                'Applied Date': app.applied_date.strftime('%Y-%m-%d'),
                'Application Method': app.application_method,
                'Response Received': 'Yes' if app.response_received else 'No',
                'Interview Scheduled': 'Yes' if app.interview_scheduled else 'No',
                'Notes': app.notes or '',
                'Next Step': app.next_step or '',
                'Next Step Date': app.next_step_date.strftime('%Y-%m-%d') if app.next_step_date else ''
            })


        return {
            'data': export_data,
            'total_records': len(export_data),
            'format': format,
            'exported_at': datetime.utcnow()
        }