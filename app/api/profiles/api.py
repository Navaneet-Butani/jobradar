"""Job profile CRUD endpoints."""

from typing import List
from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session
from ...core.responses import APIResponse
from ...core.exceptions import NotFoundError
from ...decorators.api_decorators import log_api_call, standardize_response
from ...decorators.auth_decorators import get_current_verified_user
from ...models import UserDB
from .service import ProfilesService
from ..resume.service import ResumeService
from ...services.resume_profile import suggest_profile
from .schema import JobProfileCreateRequest, JobProfileUpdateRequest, JobProfileResponse

router = APIRouter(prefix="/v1/profiles", tags=["profiles"])
profiles_service = ProfilesService()


@router.get("", response_model=List[JobProfileResponse])
@log_api_call()
@standardize_response(success_message="Profiles retrieved successfully")
async def list_profiles(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    profiles = await profiles_service.list_profiles(current_user.id, session)
    return APIResponse.success(data=[JobProfileResponse.model_validate(p) for p in profiles])


@router.post("", response_model=JobProfileResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Profile created successfully")
async def create_profile(
    request: JobProfileCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        profile = await profiles_service.create_profile(current_user.id, request, session)
        await session.commit()
        return APIResponse.created(data=JobProfileResponse.model_validate(profile))
    except Exception:
        await session.rollback()
        raise


@router.post("/suggest-from-resume")
@log_api_call()
@standardize_response(success_message="Profile suggestion generated")
async def suggest_from_resume(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    """Profile fields suggested from the user's uploaded resume. Never saves:
    the UI fills the form and the user reviews and saves it."""
    resume = await ResumeService().get_resume(current_user.id, session)
    if resume is None or not (resume.content_text or "").strip():
        return APIResponse.not_found("Upload your resume first (Profile page), then try again.")
    return APIResponse.success(data=await suggest_profile(resume.content_text))


@router.get("/{profile_id}", response_model=JobProfileResponse)
@log_api_call()
@standardize_response(success_message="Profile retrieved successfully")
async def get_profile(
    profile_id: int = Path(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        profile = await profiles_service.get_owned_profile(current_user.id, profile_id, session)
        return APIResponse.success(data=JobProfileResponse.model_validate(profile))
    except NotFoundError as e:
        return APIResponse.not_found(str(e))


@router.patch("/{profile_id}", response_model=JobProfileResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Profile updated successfully")
async def update_profile(
    request: JobProfileUpdateRequest,
    profile_id: int = Path(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        profile = await profiles_service.update_profile(current_user.id, profile_id, request, session)
        await session.commit()
        return APIResponse.success(data=JobProfileResponse.model_validate(profile))
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise


@router.delete("/{profile_id}")
@log_api_call()
@standardize_response(success_message="Profile deleted successfully")
async def delete_profile(
    profile_id: int = Path(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        await profiles_service.delete_profile(current_user.id, profile_id, session)
        await session.commit()
        return APIResponse.no_content("Profile deleted successfully")
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise
