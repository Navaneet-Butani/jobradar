"""Invite endpoints — the admin side, plus the two public ones the accept page
needs before anybody is logged in."""

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session
from ...core.exceptions import NotFoundError, ValidationError
from ...core.responses import APIResponse
from ...decorators.api_decorators import log_api_call, standardize_response
from ...decorators.auth_decorators import get_current_admin_user
from ...models import UserDB
from ...services.auth.session_service import DeviceInfo
from ..auth.schema import AuthResponse, TokenResponse, UserProfileResponse
from .schema import (
    InviteAcceptRequest,
    InviteCreateRequest,
    InviteCreateResponse,
    InvitePreviewResponse,
    MemberListResponse,
    MemberUpdateRequest,
)
from .service import InvitesService

router = APIRouter(prefix="/v1/invites", tags=["invites"])
invites_service = InvitesService()


def _device_info(request: Request) -> DeviceInfo:
    return DeviceInfo(
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        platform=request.headers.get("sec-ch-ua-platform", "").strip('"'),
        browser=None,
    )


@router.get("/members", response_model=MemberListResponse)
@log_api_call()
@standardize_response(success_message="Members retrieved successfully")
async def list_members(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_admin_user),
):
    """Everyone on the deployment, accepted or still pending."""
    members = await invites_service.list_members(session, current_user)
    return APIResponse.success(data=MemberListResponse(members=members).model_dump())


@router.post("", response_model=InviteCreateResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Invite created successfully")
async def create_invite(
    payload: InviteCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_admin_user),
):
    try:
        member, emailed, error = await invites_service.create_invite(
            email=str(payload.email),
            first_name=payload.first_name,
            last_name=payload.last_name,
            session=session,
            caller=current_user,
        )
        await session.commit()
        return APIResponse.success(
            data=InviteCreateResponse(member=member, emailed=emailed, email_error=error).model_dump()
        )
    except ValidationError as e:
        await session.rollback()
        return APIResponse.validation_error(str(e))
    except Exception:
        await session.rollback()
        raise


@router.patch("/{user_id}")
@log_api_call(log_request=True)
@standardize_response(success_message="Account updated successfully")
async def update_member(
    payload: MemberUpdateRequest,
    user_id: int = Path(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_admin_user),
):
    """Switch an account off (or back on). Never deletes — the person's matches,
    applications and outreach history stay exactly where they are."""
    try:
        member = await invites_service.set_active(user_id, payload.is_active, session, current_user)
        await session.commit()
        return APIResponse.success(data=member.model_dump())
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except ValidationError as e:
        await session.rollback()
        return APIResponse.validation_error(str(e))
    except Exception:
        await session.rollback()
        raise


@router.delete("/{user_id}")
@log_api_call()
@standardize_response(success_message="Invite revoked successfully")
async def revoke_invite(
    user_id: int = Path(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_admin_user),
):
    """Only ever removes an unaccepted invite; a claimed account is refused."""
    try:
        await invites_service.revoke(user_id, session, current_user)
        await session.commit()
        return APIResponse.success(data={"id": user_id})
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except ValidationError as e:
        await session.rollback()
        return APIResponse.validation_error(str(e))
    except Exception:
        await session.rollback()
        raise


# --------------------------------------------------------------- public pair
# Both are unauthenticated by necessity: the invitee has no account yet. The
# token in the path is the only credential, which is why it is long, single-use
# and expires.


@router.get("/accept/{token}", response_model=InvitePreviewResponse)
@log_api_call()
@standardize_response(success_message="Invite retrieved successfully")
async def preview_invite(
    token: str = Path(..., min_length=16),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        return APIResponse.success(data=InvitePreviewResponse(**await invites_service.preview(token, session)))
    except NotFoundError as e:
        return APIResponse.not_found(str(e))
    except ValidationError as e:
        return APIResponse.validation_error(str(e))


@router.post("/accept/{token}", response_model=AuthResponse)
@log_api_call()
@standardize_response(success_message="Account created successfully")
async def accept_invite(
    payload: InviteAcceptRequest,
    http_request: Request,
    token: str = Path(..., min_length=16),
    session: AsyncSession = Depends(get_db_session),
):
    """Claims the invite and signs the new user straight in — asking them to
    log in again with the password they just chose is a pointless extra step."""
    try:
        result = await invites_service.accept(
            token=token,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            device_info=_device_info(http_request),
            session=session,
        )
        await session.commit()

        tokens = result["tokens"]
        return APIResponse.success(
            data=AuthResponse(
                user=UserProfileResponse.model_validate(result["user"]),
                tokens=TokenResponse(
                    access_token=tokens.access_token,
                    refresh_token=tokens.refresh_token,
                    token_type=tokens.token_type,
                    expires_in=tokens.expires_in,
                ),
                session_id=result["session_id"],
                is_new_user=True,
            )
        )
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except ValidationError as e:
        await session.rollback()
        return APIResponse.validation_error(str(e))
    except Exception:
        await session.rollback()
        raise
