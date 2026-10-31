"""Company profile endpoints."""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session
from ...core.exceptions import NotFoundError
from ...core.responses import APIResponse
from ...decorators.api_decorators import log_api_call, standardize_response
from ...decorators.auth_decorators import get_current_verified_user
from ...models import UserDB
from .schema import CompanyResponse
from .service import CompaniesService

router = APIRouter(prefix="/v1/companies", tags=["companies"])
companies_service = CompaniesService()


@router.get("/{company_id}", response_model=CompanyResponse)
@log_api_call()
@standardize_response(success_message="Company retrieved successfully")
async def get_company(
    company_id: int = Path(..., ge=1),
    job_limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        return APIResponse.success(
            data=await companies_service.get_company(company_id, session, job_limit=job_limit)
        )
    except NotFoundError as e:
        return APIResponse.not_found(str(e))
