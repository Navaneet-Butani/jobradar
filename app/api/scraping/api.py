"""Scraping configuration endpoints — which role categories we collect."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session
from ...core.responses import APIResponse
from ...decorators.api_decorators import log_api_call, standardize_response
from ...decorators.auth_decorators import get_current_verified_user, get_current_admin_user
from ...models import UserDB
from .schema import RoleCategoriesResponse, RoleCategoriesUpdateRequest
from .service import ScrapingService

router = APIRouter(prefix="/v1/scraping", tags=["scraping"])
scraping_service = ScrapingService()


@router.get("/roles", response_model=RoleCategoriesResponse)
@log_api_call()
@standardize_response(success_message="Role categories retrieved successfully")
async def list_role_categories(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    """Every category and whether it is currently collected.

    Readable by every account — seeing what the pipeline collects is not
    privileged — but `editable` tells the UI whether to render the form as
    read-only.
    """
    categories = await scraping_service.list_categories(session)
    return APIResponse.success(
        data=RoleCategoriesResponse(
            categories=categories,
            editable=bool(current_user.is_admin),
        ).model_dump()
    )


@router.put("/roles", response_model=RoleCategoriesResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Role categories updated successfully")
async def update_role_categories(
    payload: RoleCategoriesUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_admin_user),
):
    """Replace the enabled set. Admin only — this changes what the whole
    pipeline ingests for every user, not just the caller's feed."""
    unknown = scraping_service.unknown_keys(payload.enabled)
    if unknown:
        return APIResponse.validation_error(
            message=f"Unknown role categories: {', '.join(unknown)}"
        )

    # An empty list would quietly stop the ATS adapter collecting anything.
    # Refuse it rather than let a misclick empty the corpus.
    if not payload.enabled:
        return APIResponse.validation_error(
            message="Select at least one role category"
        )

    categories = await scraping_service.update_categories(session, payload.enabled)
    return APIResponse.success(
        data=RoleCategoriesResponse(categories=categories, editable=True).model_dump()
    )
