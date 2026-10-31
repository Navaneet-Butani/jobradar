"""Authentication decorators for FastAPI endpoints."""

import functools
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Callable, Any

from ..services.auth import TokenService
from ..models import UserDB
from ..core.database import db


security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserDB:
    """Dependency to get current authenticated user."""
    try:
        user = await TokenService.get_user_from_token(credentials.credentials)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(request: Request) -> Optional[UserDB]:
    """Dependency to get current user (optional - doesn't raise if not authenticated)."""
    try:
        auth_header = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ")[1]
        user = await TokenService.get_user_from_token(token)

        return user

    except Exception:
        return None


async def get_current_active_user(current_user: UserDB = Depends(get_current_user)) -> UserDB:
    """Dependency to get current active user."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    return current_user


async def get_current_verified_user(current_user: UserDB = Depends(get_current_active_user)) -> UserDB:
    """Dependency to get current verified user."""
    from ..config.settings import settings

    if settings.require_email_verification and not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email verification required"
        )

    return current_user


async def get_current_admin_user(current_user: UserDB = Depends(get_current_verified_user)) -> UserDB:
    """Dependency for endpoints that change deployment-wide settings.

    Only guards settings that affect what the whole pipeline collects, not
    per-user data — there are two accounts and both own their own profiles.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return current_user


def require_auth(func: Callable) -> Callable:
    """Decorator to require authentication for endpoint."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Check if current_user is already in kwargs (from dependency injection)
        if 'current_user' not in kwargs:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )

        return await func(*args, **kwargs)

    return wrapper


def require_verified_user(func: Callable) -> Callable:
    """Decorator to require verified user for endpoint."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        current_user = kwargs.get('current_user')

        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )

        from ..config.settings import settings

        if settings.require_email_verification and not current_user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email verification required"
            )

        return await func(*args, **kwargs)

    return wrapper


def require_subscription(min_plan: str = "free"):
    """Decorator to require specific subscription level."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )

            # TODO: Implement subscription level checking
            # For now, just check if user has active subscription
            # This would be implemented based on subscription levels

            return await func(*args, **kwargs)

        return wrapper

    return decorator


class PermissionChecker:
    """Helper class for permission checking."""

    @staticmethod
    async def check_user_permission(user: UserDB, resource: str, action: str) -> bool:
        """Check if user has permission for resource action."""
        # Basic permission checking - can be extended for RBAC
        if not user.is_active:
            return False

        # For now, all active users have basic permissions
        # This can be extended with role-based permissions
        return True

    @staticmethod
    async def check_resource_ownership(user: UserDB, resource_id: int, resource_type: str) -> bool:
        """Check if user owns the resource."""
        # This would check if user owns the specific resource
        # Implementation depends on resource type
        return True


def require_permission(resource: str, action: str):
    """Decorator to require specific permission."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )

            has_permission = await PermissionChecker.check_user_permission(
                current_user, resource, action
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions"
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_ownership(resource_type: str, resource_id_param: str = "id"):
    """Decorator to require resource ownership."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )

            resource_id = kwargs.get(resource_id_param)

            if not resource_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Resource ID required"
                )

            owns_resource = await PermissionChecker.check_resource_ownership(
                current_user, resource_id, resource_type
            )

            if not owns_resource:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied - you don't own this resource"
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator