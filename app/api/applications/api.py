"""Application tracking API endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session
from ...core.responses import APIResponse
from ...core.exceptions import NotFoundError
from ...decorators.api_decorators import log_api_call, standardize_response
from ...decorators.auth_decorators import get_current_verified_user
from ...models import UserDB
from ...models.common import ApplicationStatus
from .service import ApplicationsService
from .schema import (
    CreateApplicationRequest, UpdateApplicationRequest, ApplicationListResponse,
    ApplicationStatsResponse, FollowUpApplicationsResponse, ApplicationTimelineResponse,
    StatusUpdateRequest, ApplicationSummaryResponse, ApplicationNotesUpdateRequest,
    ApplicationDeleteResponse, DueTodayResponse
)

router = APIRouter(prefix="/v1/applications", tags=["applications"])
applications_service = ApplicationsService()


@router.post("", response_model=dict)
@log_api_call(log_request=True)
@standardize_response(success_message="Application tracking created successfully")
async def create_application(
    request: CreateApplicationRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Create new application tracking record."""
    try:
        application = await applications_service.create_application(
            user_id=current_user.id,
            application_data=request,
            session=session
        )

        # Track activity
        await applications_service.track_application_activity(
            user_id=current_user.id,
            application_id=application.id,
            action="create",
            details={'job_id': request.job_id, 'status': request.status},
            session=session
        )

        await session.commit()
        return APIResponse.success(data=application)

    except ValueError as e:
        return APIResponse.error(message=str(e), status_code=409)
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=ApplicationListResponse)
@log_api_call()
@standardize_response(success_message="Applications retrieved")
async def get_applications(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Number of applications to return"),
    offset: int = Query(0, ge=0, description="Number of applications to skip"),
    sort_by: str = Query("applied_date", pattern="^(applied_date|status|company_name|response_date)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Get user's application tracking records."""
    try:
        applications_list = await applications_service.get_user_applications(
            user_id=current_user.id,
            status=status,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            session=session
        )

        await session.commit()  # persists any auto-ghost sweep run as part of the fetch
        return APIResponse.success(data=applications_list)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/due-today", response_model=DueTodayResponse)
@log_api_call()
@standardize_response(success_message="Due-today applications retrieved")
async def get_due_today(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Applications with a follow-up due today or earlier."""
    try:
        due = await applications_service.get_due_today(user_id=current_user.id, session=session)
        await session.commit()
        return APIResponse.success(data=due)

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{application_id}")
@log_api_call(log_request=True)
@standardize_response(success_message="Application updated successfully")
async def update_application(
    application_id: int,
    request: UpdateApplicationRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Update application tracking record."""
    try:
        application = await applications_service.update_application(
            user_id=current_user.id,
            application_id=application_id,
            update_data=request,
            session=session
        )

        if not application:
            return APIResponse.not_found("Application not found")

        # Track activity
        await applications_service.track_application_activity(
            user_id=current_user.id,
            application_id=application_id,
            action="update",
            details=request.model_dump(exclude_unset=True),
            session=session
        )

        await session.commit()
        return APIResponse.success(data=application)

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{application_id}/status")
@log_api_call(log_request=True)
@standardize_response(success_message="Application status updated")
async def update_application_status(
    application_id: int,
    request: StatusUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Update application status with additional tracking fields."""
    try:
        application = await applications_service.update_application_status(
            user_id=current_user.id,
            application_id=application_id,
            status=request.status,
            notes=request.notes,
            response_received=request.response_received,
            response_date=request.response_date,
            interview_scheduled=request.interview_scheduled,
            next_step=request.next_step,
            next_step_date=request.next_step_date,
            session=session
        )

        if not application:
            return APIResponse.not_found("Application not found")

        # Track activity
        await applications_service.track_application_activity(
            user_id=current_user.id,
            application_id=application_id,
            action="status_update",
            details={'new_status': request.status.value},
            session=session
        )

        await session.commit()
        return APIResponse.success(data=application)

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{application_id}/draft-followup")
@log_api_call()
@standardize_response(success_message="Draft generated")
async def draft_followup(
    application_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Generate an LLM follow-up message draft. The user reviews and sends it themselves."""
    try:
        draft = await applications_service.draft_followup(
            user_id=current_user.id,
            application_id=application_id,
            session=session
        )
        if draft is None:
            return APIResponse.error(
                message="Draft generation is unavailable right now (LLM not configured or the call failed).",
                status_code=503
            )
        return APIResponse.success(data={"draft": draft})

    except NotFoundError as e:
        return APIResponse.not_found(str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{application_id}/notes")
@log_api_call(log_request=True)
@standardize_response(success_message="Application notes updated")
async def update_application_notes(
    application_id: int,
    request: ApplicationNotesUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Update application notes."""
    try:
        application = await applications_service.update_application_notes(
            user_id=current_user.id,
            application_id=application_id,
            notes=request.notes,
            session=session
        )

        if not application:
            return APIResponse.not_found("Application not found")

        await session.commit()
        return APIResponse.success(data=application)

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{application_id}", response_model=ApplicationDeleteResponse)
@log_api_call()
@standardize_response(success_message="Application deleted successfully")
async def delete_application(
    application_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Delete application tracking record."""
    try:
        success = await applications_service.delete_application(
            user_id=current_user.id,
            application_id=application_id,
            session=session
        )

        if not success:
            return APIResponse.not_found("Application not found")

        # Track activity
        await applications_service.track_application_activity(
            user_id=current_user.id,
            application_id=application_id,
            action="delete",
            session=session
        )

        await session.commit()

        response = ApplicationDeleteResponse(
            success=True,
            message="Application deleted successfully"
        )

        return APIResponse.success(data=response)

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/overview", response_model=ApplicationStatsResponse)
@log_api_call()
@standardize_response(success_message="Application statistics retrieved")
async def get_application_stats(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Get comprehensive application statistics."""
    try:
        stats = await applications_service.get_application_stats(
            user_id=current_user.id,
            session=session
        )

        return APIResponse.success(data=stats)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary", response_model=ApplicationSummaryResponse)
@log_api_call()
@standardize_response(success_message="Application summary retrieved")
async def get_application_summary(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Get application summary for dashboard."""
    try:
        summary = await applications_service.get_application_summary(
            user_id=current_user.id,
            session=session
        )

        return APIResponse.success(data=summary)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/follow-up", response_model=FollowUpApplicationsResponse)
@log_api_call()
@standardize_response(success_message="Follow-up applications retrieved")
async def get_follow_up_applications(
    days_threshold: int = Query(7, ge=1, le=30, description="Days threshold for follow-up"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Get applications that need follow-up."""
    try:
        follow_up_apps = await applications_service.get_applications_needing_follow_up(
            user_id=current_user.id,
            days_threshold=days_threshold,
            session=session
        )

        return APIResponse.success(data=follow_up_apps)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline", response_model=ApplicationTimelineResponse)
@log_api_call()
@standardize_response(success_message="Application timeline retrieved")
async def get_application_timeline(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Get applications timeline data."""
    try:
        timeline = await applications_service.get_application_timeline(
            user_id=current_user.id,
            session=session
        )

        return APIResponse.success(data=timeline)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/insights")
@log_api_call()
@standardize_response(success_message="Application insights retrieved")
async def get_application_insights(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Get application insights and recommendations."""
    try:
        insights = await applications_service.get_application_insights(
            user_id=current_user.id,
            session=session
        )

        return APIResponse.success(data=insights)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company/{company_name}")
@log_api_call()
@standardize_response(success_message="Company applications retrieved")
async def get_applications_by_company(
    company_name: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Get all applications for a specific company."""
    try:
        applications = await applications_service.get_applications_by_company(
            user_id=current_user.id,
            company_name=company_name,
            session=session
        )

        return APIResponse.success(data={
            'company_name': company_name,
            'applications': applications,
            'total_count': len(applications)
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
@log_api_call()
@standardize_response(success_message="Applications exported successfully")
async def export_applications(
    format: str = Query("csv", pattern="^(csv|json)$", description="Export format"),
    status: Optional[str] = Query(None, description="Filter by status"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Export applications data."""
    try:
        export_result = await applications_service.export_applications(
            user_id=current_user.id,
            format=format,
            status_filter=status,
            session=session
        )

        await session.commit()
        return APIResponse.success(data=export_result)

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# Registered last: literal paths above (/due-today, /stats/*, /follow-up,
# /timeline, /insights, /company/*, /export) must be matched before falling
# through to this catch-all /{application_id}.
@router.get("/{application_id}")
@log_api_call()
@standardize_response(success_message="Application retrieved")
async def get_application(
    application_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Get specific application by ID."""
    try:
        application = await applications_service.get_application_by_id(
            user_id=current_user.id,
            application_id=application_id,
            session=session
        )

        if not application:
            return APIResponse.not_found("Application not found")

        return APIResponse.success(data=application)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))