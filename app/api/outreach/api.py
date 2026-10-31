"""Outreach endpoints — sending identity, contacts, campaigns, application sends.

Route order matters: every literal path is registered before any `/{id}`
route in the same router, otherwise the catch-all swallows it.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Path, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session
from ...core.responses import APIResponse
from ...core.exceptions import NotFoundError, ValidationError
from ...decorators.api_decorators import log_api_call, standardize_response
from ...decorators.auth_decorators import get_current_verified_user
from ...models import UserDB
from ...services.outreach.runner import drain_campaign
from ...services.outreach.sender import OutreachSendError
from ...services.outreach.templates import DEFAULT_BODY, DEFAULT_SUBJECT, MERGE_FIELDS
from .service import OutreachService
from .schema import (
    ApplicationDraftResponse,
    ApplicationSendRequest,
    CampaignListResponse,
    CampaignRequest,
    CampaignResponse,
    CampaignUpdateRequest,
    ContactListResponse,
    ContactRequest,
    ContactResponse,
    ContactUpdateRequest,
    EmailAccountRequest,
    EmailAccountResponse,
    ImportResultResponse,
    PreviewRequest,
    PreviewResponse,
    SendResultResponse,
    StartCampaignResponse,
    SyncResultResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/outreach", tags=["outreach"])
outreach_service = OutreachService()


# ---------------- sending identity ----------------

@router.get("/email-account", response_model=EmailAccountResponse)
@log_api_call()
@standardize_response(success_message="Sending account retrieved")
async def get_email_account(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    account = await outreach_service.get_account(current_user.id, session)
    if account is None:
        return APIResponse.not_found("No sending account configured")
    return APIResponse.success(data=await outreach_service.account_payload(account, session))


@router.post("/email-account", response_model=EmailAccountResponse)
@log_api_call()   # never log_request=True here — the body carries the app password
@standardize_response(success_message="Sending account saved")
async def save_email_account(
    request: EmailAccountRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        account = await outreach_service.upsert_account(current_user.id, request, session)
        await session.commit()
        return APIResponse.success(data=await outreach_service.account_payload(account, session))
    except Exception:
        await session.rollback()
        raise


@router.post("/email-account/verify", response_model=EmailAccountResponse)
@log_api_call()
@standardize_response(success_message="Sending account verified")
async def verify_email_account(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        account = await outreach_service.verify_account(current_user.id, session)
        await session.commit()
        return APIResponse.success(data=await outreach_service.account_payload(account, session))
    except (ValidationError, OutreachSendError) as e:
        await session.rollback()
        return APIResponse.validation_error(str(e))
    except Exception:
        await session.rollback()
        raise


@router.delete("/email-account")
@log_api_call()
@standardize_response(success_message="Sending account removed")
async def delete_email_account(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        await outreach_service.delete_account(current_user.id, session)
        await session.commit()
        return APIResponse.no_content("Sending account removed")
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise


@router.post("/sync", response_model=SyncResultResponse)
@log_api_call()
@standardize_response(success_message="Mailbox synced")
async def sync_mailbox(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    """Read replies and bounces from the user's own mailbox, then queue any follow-ups now due.

    IMAP trouble is reported in the payload rather than raised — a mailbox we
    can't reach should degrade this feature, not break the page.
    """
    try:
        result = await outreach_service.sync_feedback(current_user.id, session)
        await session.commit()
        return APIResponse.success(data=result)
    except ValidationError as e:
        await session.rollback()
        return APIResponse.validation_error(str(e))
    except Exception:
        await session.rollback()
        raise


# ---------------- templates ----------------

@router.get("/template-defaults")
@log_api_call()
@standardize_response(success_message="Template defaults retrieved")
async def get_template_defaults(
    current_user: UserDB = Depends(get_current_verified_user),
):
    """Starter subject/body plus the merge fields that actually resolve."""
    return APIResponse.success(data={
        "subject_template": DEFAULT_SUBJECT,
        "body_template": DEFAULT_BODY,
        "merge_fields": list(MERGE_FIELDS),
    })


# ---------------- contacts ----------------

@router.get("/contacts", response_model=ContactListResponse)
@log_api_call()
@standardize_response(success_message="Contacts retrieved")
async def list_contacts(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    contacts, total = await outreach_service.list_contacts(current_user.id, session)
    return APIResponse.success(data={"contacts": contacts, "total_count": total})


@router.post("/contacts", response_model=ContactResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Contact added")
async def create_contact(
    request: ContactRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        contact = await outreach_service.create_contact(current_user.id, request, session)
        await session.commit()
        return APIResponse.created(data=outreach_service._contact_payload(contact, {}))
    except ValidationError as e:
        await session.rollback()
        return APIResponse.validation_error(str(e))
    except Exception:
        await session.rollback()
        raise


@router.post("/contacts/import", response_model=ImportResultResponse)
@log_api_call()
@standardize_response(success_message="Contacts imported")
async def import_contacts(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    """Import a CSV of contacts. Column names are matched loosely; only `email` is required."""
    try:
        data = await file.read()
        result = await outreach_service.import_contacts_csv(current_user.id, data, session)
        await session.commit()
        return APIResponse.success(data=result)
    except ValidationError as e:
        await session.rollback()
        return APIResponse.validation_error(str(e))
    except Exception:
        await session.rollback()
        raise


@router.patch("/contacts/{contact_id}", response_model=ContactResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Contact updated")
async def update_contact(
    request: ContactUpdateRequest,
    contact_id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        contact = await outreach_service.update_contact(current_user.id, contact_id, request, session)
        await session.commit()
        return APIResponse.success(data=outreach_service._contact_payload(contact, {}))
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise


@router.delete("/contacts/{contact_id}")
@log_api_call()
@standardize_response(success_message="Contact deleted")
async def delete_contact(
    contact_id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        await outreach_service.delete_contact(current_user.id, contact_id, session)
        await session.commit()
        return APIResponse.no_content("Contact deleted")
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise


# ---------------- application-side send ----------------

@router.get("/application/{application_id}/draft", response_model=ApplicationDraftResponse)
@log_api_call()
@standardize_response(success_message="Draft prepared")
async def draft_application_email(
    application_id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        return APIResponse.success(
            data=await outreach_service.draft_for_application(current_user.id, application_id, session)
        )
    except ValidationError as e:
        return APIResponse.validation_error(str(e))
    except NotFoundError as e:
        return APIResponse.not_found(str(e))


@router.post("/send", response_model=SendResultResponse)
@log_api_call()
@standardize_response(success_message="Email sent")
async def send_application_email(
    request: ApplicationSendRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    """Send one outreach email tied to a tracked application. Logged and capped like any other send."""
    try:
        result = await outreach_service.send_from_application(current_user.id, request, session)
        await session.commit()
        return APIResponse.success(data=result)
    except ValidationError as e:
        await session.commit()   # keep the failed-message row for the history
        return APIResponse.validation_error(str(e))
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise


# ---------------- campaigns ----------------

@router.post("/campaigns/preview", response_model=PreviewResponse)
@log_api_call()
@standardize_response(success_message="Preview generated")
async def preview_campaign(
    request: PreviewRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    """Render what each recipient would actually receive. Sends nothing."""
    try:
        return APIResponse.success(data=await outreach_service.preview(current_user.id, request, session))
    except ValidationError as e:
        return APIResponse.validation_error(str(e))
    except NotFoundError as e:
        return APIResponse.not_found(str(e))


@router.get("/campaigns", response_model=CampaignListResponse)
@log_api_call()
@standardize_response(success_message="Campaigns retrieved")
async def list_campaigns(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    campaigns, total = await outreach_service.list_campaigns(current_user.id, session)
    return APIResponse.success(data={"campaigns": campaigns, "total_count": total})


@router.post("/campaigns", response_model=CampaignResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Campaign created")
async def create_campaign(
    request: CampaignRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    """Build the campaign and queue one message per contact. Nothing sends until it's started."""
    try:
        campaign = await outreach_service.create_campaign(current_user.id, request, session)
        payload = await outreach_service.campaign_payload(campaign, session, include_messages=True)
        await session.commit()
        return APIResponse.created(data=payload)
    except ValidationError as e:
        await session.rollback()
        return APIResponse.validation_error(str(e))
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise


@router.post("/campaigns/{campaign_id}/start", response_model=StartCampaignResponse)
@log_api_call()
@standardize_response(success_message="Campaign started")
async def start_campaign(
    background_tasks: BackgroundTasks,
    campaign_id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    """Begin (or resume) sending. The drain runs in the background, paced by the account's interval."""
    try:
        result = await outreach_service.mark_running(current_user.id, campaign_id, session)
        await session.commit()
        background_tasks.add_task(drain_campaign, campaign_id, current_user.id)
        return APIResponse.success(data=result)
    except ValidationError as e:
        await session.rollback()
        return APIResponse.validation_error(str(e))
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise


@router.post("/campaigns/{campaign_id}/pause", response_model=CampaignResponse)
@log_api_call()
@standardize_response(success_message="Campaign paused")
async def pause_campaign(
    campaign_id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        campaign = await outreach_service.pause_campaign(current_user.id, campaign_id, session)
        payload = await outreach_service.campaign_payload(campaign, session)
        await session.commit()
        return APIResponse.success(data=payload)
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
@log_api_call()
@standardize_response(success_message="Campaign retrieved")
async def get_campaign(
    campaign_id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        campaign = await outreach_service.get_owned_campaign(current_user.id, campaign_id, session)
        return APIResponse.success(
            data=await outreach_service.campaign_payload(campaign, session, include_messages=True)
        )
    except NotFoundError as e:
        return APIResponse.not_found(str(e))


@router.patch("/campaigns/{campaign_id}", response_model=CampaignResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Campaign updated")
async def update_campaign(
    request: CampaignUpdateRequest,
    campaign_id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        campaign = await outreach_service.update_campaign(current_user.id, campaign_id, request, session)
        payload = await outreach_service.campaign_payload(campaign, session)
        await session.commit()
        return APIResponse.success(data=payload)
    except ValidationError as e:
        await session.rollback()
        return APIResponse.validation_error(str(e))
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise


@router.delete("/campaigns/{campaign_id}")
@log_api_call()
@standardize_response(success_message="Campaign deleted")
async def delete_campaign(
    campaign_id: int = Path(..., gt=0),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user),
):
    try:
        await outreach_service.delete_campaign(current_user.id, campaign_id, session)
        await session.commit()
        return APIResponse.no_content("Campaign deleted")
    except NotFoundError as e:
        await session.rollback()
        return APIResponse.not_found(str(e))
    except Exception:
        await session.rollback()
        raise
