"""Authentication API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session
from ...config.settings import settings
from ...core.responses import APIResponse
from ...decorators.api_decorators import log_api_call, standardize_response
from ...decorators.auth_decorators import get_current_user, get_current_user_optional, get_current_verified_user
from ...services.auth import (
    RegistrationService, LoginService, TokenService,
    SessionService, SecurityAuditService,
    UserRegistration, LoginCredentials, DeviceInfo
)
from ...services.auth.password_service import PasswordService
from ...services.email_service import EmailService
from ...models import UserDB
from .schema import (
    UserRegistrationRequest, LoginRequest, PasswordResetRequest,
    PasswordResetConfirm, PasswordChangeRequest, TokenRefreshRequest,
    EmailVerificationRequest, ResendVerificationRequest,
    AuthResponse, TokenResponse, UserProfileResponse,
    MessageResponse, UserSessionsResponse,
    PasswordValidationResponse
)

router = APIRouter(prefix="/v1/auth", tags=["authentication"])


def get_device_info(request: Request) -> DeviceInfo:
    """Extract device information from request."""
    return DeviceInfo(
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host,
        platform=request.headers.get("sec-ch-ua-platform", "").strip('"'),
        browser=request.headers.get("sec-ch-ua", "").split(";")[0].strip('"') if request.headers.get("sec-ch-ua") else None
    )


@router.post("/register", response_model=AuthResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Registration successful")
async def register(
    request: UserRegistrationRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_db_session)
):
    """Register a new user account."""
    if not settings.allow_registration:
        return APIResponse.forbidden(
            message="Registration is closed. JobRadar is invite-only."
        )

    device_info = get_device_info(http_request)

    registration_data = UserRegistration(
        email=request.email,
        password=request.password,
        first_name=request.first_name,
        last_name=request.last_name
    )

    result = await RegistrationService.register_user(registration_data, device_info, session)

    if not result.success:
        return APIResponse.error(
            message=result.message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=result.errors
        )

    # Create response
    user_profile = UserProfileResponse.model_validate(result.user)
    tokens = TokenResponse(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        token_type=result.tokens.token_type,
        expires_in=result.tokens.expires_in
    )

    auth_response = AuthResponse(
        user=user_profile,
        tokens=tokens,
        session_id=result.session_id,
        is_new_user=True
    )

    return APIResponse.success(data=auth_response)


@router.post("/login", response_model=AuthResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Login successful")
async def login(
    request: LoginRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_db_session)
):
    """Authenticate user and create session."""
    device_info = get_device_info(http_request)

    credentials = LoginCredentials(
        email=request.email,
        password=request.password,
        remember_me=request.remember_me
    )

    result = await LoginService.login(credentials, device_info, session)

    if not result.success:
        if result.requires_verification:
            return APIResponse.error(
                message=result.message,
                error_code="EMAIL_VERIFICATION_REQUIRED",
                status_code=status.HTTP_403_FORBIDDEN,
                details=result.errors
            )

        return APIResponse.unauthorized(message=result.message)

    # Create response
    user_profile = UserProfileResponse.model_validate(result.user)
    tokens = TokenResponse(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        token_type=result.tokens.token_type,
        expires_in=result.tokens.expires_in
    )

    auth_response = AuthResponse(
        user=user_profile,
        tokens=tokens,
        session_id=result.session_id,
        is_new_user=False
    )

    return APIResponse.success(data=auth_response)


@router.post("/logout", response_model=MessageResponse)
@log_api_call()
@standardize_response(success_message="Logout successful")
async def logout(
    session_id: str = Query(..., description="Session ID to logout"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_user)
):
    """Logout user from current session."""
    success = await LoginService.logout(session_id, session)

    if not success:
        return APIResponse.error(message="Failed to logout session")

    return APIResponse.success(data={"message": "Logged out successfully"})


@router.post("/logout-all", response_model=MessageResponse)
@log_api_call()
@standardize_response(success_message="Logged out from all devices")
async def logout_all_devices(
    current_session_id: str = Query(None, description="Current session ID to keep active"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_user)
):
    """Logout user from all devices except current."""
    terminated_count = await LoginService.logout_all_devices(
        user_id=current_user.id,
        current_session_id=current_session_id,
        session=session
    )

    return APIResponse.success(
        data={"message": f"Logged out from {terminated_count} devices"}
    )


@router.post("/refresh", response_model=TokenResponse)
@log_api_call()
@standardize_response(success_message="Token refreshed successfully")
async def refresh_token(
    request: TokenRefreshRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Refresh access token using refresh token."""
    result = await LoginService.refresh_tokens(request.refresh_token, session)

    if not result.success:
        return APIResponse.unauthorized(message=result.message)

    tokens = TokenResponse(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        token_type=result.tokens.token_type,
        expires_in=result.tokens.expires_in
    )

    return APIResponse.success(data=tokens)


@router.get("/me", response_model=UserProfileResponse)
@log_api_call()
@standardize_response(success_message="User profile retrieved")
async def get_current_user_profile(
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Get current authenticated user profile."""
    user_profile = UserProfileResponse.model_validate(current_user)
    return APIResponse.success(data=user_profile)


@router.get("/sessions", response_model=UserSessionsResponse)
@log_api_call()
@standardize_response(success_message="User sessions retrieved")
async def get_user_sessions(
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_user)
):
    """Get all active sessions for current user."""
    sessions = await SessionService.get_user_sessions(current_user.id, session)

    session_infos = []
    for session_info in sessions:
        session_infos.append({
            "session_id": session_info.session_id,
            "device_info": session_info.device_info.to_dict(),
            "ip_address": session_info.device_info.ip_address,
            "created_at": session_info.created_at,
            "last_activity": session_info.last_activity,
            "expires_at": session_info.expires_at,
            "is_current": session_info.is_current
        })

    response = UserSessionsResponse(
        sessions=session_infos,
        total_count=len(session_infos)
    )

    return APIResponse.success(data=response)


# Password Management
@router.post("/password/reset-request", response_model=MessageResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Password reset email sent")
async def request_password_reset(
    request: PasswordResetRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_db_session)
):
    """Request password reset email."""
    device_info = get_device_info(http_request)

    result = await PasswordService.request_password_reset(
        email=request.email,
        device_info=device_info,
        session=session
    )

    if not result.success:
        return APIResponse.error(
            message=result.message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=result.errors
        )

    return APIResponse.success(data={"message": result.message})


@router.post("/password/reset", response_model=MessageResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Password reset successfully")
async def reset_password(
    request: PasswordResetConfirm,
    http_request: Request,
    session: AsyncSession = Depends(get_db_session)
):
    """Reset password using reset token."""
    device_info = get_device_info(http_request)

    result = await PasswordService.reset_password(
        token=request.token,
        new_password=request.new_password,
        device_info=device_info,
        session=session
    )

    if not result.success:
        return APIResponse.error(
            message=result.message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=result.errors
        )

    return APIResponse.success(data={"message": result.message})


@router.post("/password/change", response_model=MessageResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Password changed successfully")
async def change_password(
    request: PasswordChangeRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserDB = Depends(get_current_verified_user)
):
    """Change password for authenticated user."""
    device_info = get_device_info(http_request)

    result = await PasswordService.change_password(
        user_id=current_user.id,
        current_password=request.current_password,
        new_password=request.new_password,
        device_info=device_info,
        session=session
    )

    if not result.success:
        return APIResponse.error(
            message=result.message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=result.errors
        )

    # Send notification email
    if EmailService.is_email_configured():
        await EmailService.send_password_changed_notification(
            email=current_user.email,
            user_name=getattr(current_user.profile, 'first_name', None) if hasattr(current_user, 'profile') else None,
            ip_address=device_info.ip_address
        )

    return APIResponse.success(data={"message": result.message})


# Email Verification
@router.post("/verify-email", response_model=MessageResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Email verified successfully")
async def verify_email(
    request: EmailVerificationRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Verify user email with verification token."""
    result = await RegistrationService.verify_email(request.token, session)

    if not result.success:
        return APIResponse.error(
            message=result.message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=result.errors
        )

    return APIResponse.success(data={"message": result.message})


@router.post("/resend-verification", response_model=MessageResponse)
@log_api_call(log_request=True)
@standardize_response(success_message="Verification email sent")
async def resend_verification_email(
    request: ResendVerificationRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_db_session)
):
    """Resend email verification."""
    device_info = get_device_info(http_request)

    result = await RegistrationService.resend_verification_email(
        email=request.email,
        device_info=device_info,
        session=session
    )

    if not result.success:
        return APIResponse.error(
            message=result.message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=result.errors
        )

    return APIResponse.success(data={"message": result.message})



# Utility endpoints
@router.get("/validate-token")
@log_api_call()
@standardize_response(success_message="Token is valid")
async def validate_token(
    current_user: UserDB = Depends(get_current_user_optional)
):
    """Validate current token (for frontend use)."""
    if not current_user:
        return APIResponse.unauthorized(message="Invalid or expired token")

    return APIResponse.success(data={"valid": True, "user_id": current_user.id})