"""Application packet endpoint. Body-only, no path params — nothing to shadow."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session
from ...core.responses import APIResponse
from ...core.exceptions import NotFoundError
from ...decorators.api_decorators import log_api_call, standardize_response
from ...decorators.auth_decorators import get_current_verified_user
from ...models import UserDB
from .service import PacketService
from .schema import PacketRequest, PacketResponse

router = APIRouter(prefix="/v1/packet", tags=["packet"])
packet_service = PacketService()


@router.post("", response_model=PacketResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Packet generated")
async def generate_packet(
    request: PacketRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    """Assemble an application packet for one job. Never submits or sends anything."""
    try:
        packet = await packet_service.generate(
            user_id=current_user.id,
            job_id=request.job_id,
            profile_id=request.profile_id,
            session=session,
        )
        if packet is None:
            return APIResponse.not_found("Job not found")
        # Careers-page discovery caches its result on the company row.
        await session.commit()
        return APIResponse.success(data=PacketResponse.model_validate(packet))
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise
