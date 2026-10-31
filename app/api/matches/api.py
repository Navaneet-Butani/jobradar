"""Match feed endpoints — the ranked list, state transitions, and stats."""

from typing import Optional
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session
from ...core.responses import APIResponse
from ...core.exceptions import NotFoundError, ValidationError
from ...decorators.api_decorators import log_api_call, standardize_response
from ...decorators.auth_decorators import get_current_verified_user
from ...models import UserDB
from .service import MatchesService
from .schema import MatchStateUpdateRequest, MatchListResponse, MatchStatsResponse, MatchJobResponse

router = APIRouter(prefix="/v1/matches", tags=["matches"])
matches_service = MatchesService()


@router.get("", response_model=MatchListResponse)
@log_api_call()
@standardize_response(success_message="Matches retrieved successfully")
async def get_matches(
    profile_id: int = Query(..., description="job_profile id to fetch the feed for"),
    state: Optional[str] = Query(None, pattern="^(new|seen|interested|applied|dismissed)$"),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    remote_only: bool = Query(False),
    my_cities_only: bool = Query(False),
    sort: str = Query("score", pattern="^(score|newest)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        matches, total_count = await matches_service.get_feed(
            user_id=current_user.id,
            profile_id=profile_id,
            session=session,
            state=state,
            min_score=min_score,
            remote_only=remote_only,
            my_cities_only=my_cities_only,
            sort=sort,
            page=page,
            limit=limit,
        )
        return APIResponse.success(
            data=MatchListResponse(matches=matches, total_count=total_count, page=page, limit=limit)
        )
    except NotFoundError as e:
        return APIResponse.not_found(str(e))


@router.get("/stats", response_model=MatchStatsResponse)
@log_api_call()
@standardize_response(success_message="Match stats retrieved successfully")
async def get_match_stats(
    profile_id: int = Query(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        stats = await matches_service.get_stats(current_user.id, profile_id, session)
        return APIResponse.success(data=MatchStatsResponse(**stats))
    except NotFoundError as e:
        return APIResponse.not_found(str(e))


@router.get("/states")
@log_api_call()
@standardize_response(success_message="Match states retrieved successfully")
async def get_match_states(
    profile_id: int = Query(...),
    job_ids: str = Query(..., description="Comma-separated job ids, at most 100"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    """Which of these jobs are already in the caller's feed, and in what state.

    Declared before /{job_id} on purpose — FastAPI matches in definition order,
    so the other way round "states" would be parsed as a job id.
    """
    try:
        ids = [int(part) for part in job_ids.split(",") if part.strip().isdigit()][:100]
    except ValueError:
        return APIResponse.validation_error("job_ids must be a comma-separated list of integers")

    try:
        states = await matches_service.get_states(current_user.id, profile_id, ids, session)
        return APIResponse.success(data={"states": states})
    except NotFoundError as e:
        return APIResponse.not_found(str(e))


@router.get("/{job_id}", response_model=MatchJobResponse)
@log_api_call()
@standardize_response(success_message="Match retrieved successfully")
async def get_match(
    job_id: int = Path(...),
    profile_id: int = Query(..., description="job_profile id this match belongs to"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        match = await matches_service.get_single(current_user.id, profile_id, job_id, session)
        if match is None:
            return APIResponse.not_found("Match not found")
        return APIResponse.success(data=match)
    except NotFoundError as e:
        return APIResponse.not_found(str(e))


@router.patch("/{job_id}/state")
@log_api_call(log_request=True)
@standardize_response(success_message="Match state updated successfully")
async def update_match_state(
    request: MatchStateUpdateRequest,
    job_id: int = Path(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        match = await matches_service.update_state(
            user_id=current_user.id,
            profile_id=request.profile_id,
            job_id=job_id,
            new_state=request.state,
            session=session,
        )
        await session.commit()
        return APIResponse.success(data={"job_id": job_id, "state": match.state})
    except (NotFoundError, ValidationError) as e:
        await session.rollback()
        if isinstance(e, NotFoundError):
            return APIResponse.not_found(str(e))
        return APIResponse.validation_error(str(e))
    except Exception:
        await session.rollback()
        raise
