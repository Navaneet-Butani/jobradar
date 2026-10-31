"""Master resume endpoints — upload, read, delete. No path params, so no route-ordering trap."""

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session
from ...core.responses import APIResponse
from ...core.exceptions import NotFoundError, ValidationError
from ...decorators.api_decorators import log_api_call, standardize_response
from ...decorators.auth_decorators import get_current_verified_user
from ...models import UserDB
from .service import ResumeService
from .schema import ResumeResponse

router = APIRouter(prefix="/v1/resume", tags=["resume"])
resume_service = ResumeService()


@router.get("", response_model=ResumeResponse)
@log_api_call()
@standardize_response(success_message="Resume retrieved successfully")
async def get_resume(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    resume = await resume_service.get_resume(current_user.id, session)
    if resume is None:
        return APIResponse.not_found("No resume on file")
    return APIResponse.success(data=ResumeResponse.model_validate(resume))


@router.post("", response_model=ResumeResponse)
@log_api_call()
@standardize_response(success_message="Resume uploaded successfully")
async def upload_resume(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    """Upload a PDF/DOCX/TXT resume. The text is extracted and stored; the file itself is not kept."""
    try:
        data = await file.read()
        resume = await resume_service.upsert_resume(
            user_id=current_user.id,
            filename=file.filename or "resume",
            content_type=file.content_type,
            data=data,
            session=session,
        )
        await session.commit()
        return APIResponse.success(data=ResumeResponse.model_validate(resume))
    except ValidationError as e:
        await session.rollback()
        return APIResponse.validation_error(str(e))
    except Exception:
        await session.rollback()
        raise


@router.delete("")
@log_api_call()
@standardize_response(success_message="Resume deleted successfully")
async def delete_resume(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        await resume_service.delete_resume(current_user.id, session)
        await session.commit()
        return APIResponse.no_content("Resume deleted successfully")
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise
