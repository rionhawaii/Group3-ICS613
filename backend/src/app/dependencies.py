"""Common FastAPI dependencies."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    PermissionDeniedError,
)
from app.core.security import decode_token
from app.db.session import get_db
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.services.user import UserService

# Reusable security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Validate JWT access token and return the authenticated user.

    Raises the project's domain exceptions (``AuthenticationError``) on
    failure so the response shape stays consistent with the rest of the API
    (``{detail, error_code, ...}``) and is mapped to the right HTTP status
    by the central ``_handle_app_error`` handler in ``app.main``.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required")

    payload = decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type")

    jti = payload.get("jti")
    if jti:
        revoked = await db.execute(select(RevokedToken.id).where(RevokedToken.jti == jti))
        if revoked.scalar_one_or_none() is not None:
            raise AuthenticationError("Token has been revoked")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token subject")

    user = await UserService().get_by_id(db, UUID(user_id))
    if user is None:
        raise AuthenticationError("User not found")

    # Invalidate tokens issued before the last password change.
    # ``iat`` is a Unix epoch (seconds). Convert to a tz-aware UTC datetime
    # so the comparison is correct regardless of the server's local timezone.
    issued_at_epoch = payload.get("iat")
    password_changed_at = user.password_changed_at
    if issued_at_epoch and password_changed_at:
        issued_at = datetime.fromtimestamp(issued_at_epoch, tz=UTC)
        if issued_at < password_changed_at:
            raise AuthenticationError("Token revoked due to password change")

    return user


def require_user_status(*allowed_statuses: str) -> Callable:
    """Return a dependency that enforces one or more user statuses."""

    async def _checker(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if user.status.value not in allowed_statuses:
            raise PermissionDeniedError("Account status does not permit this action")
        return user

    return _checker


async def get_current_member(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require an active user."""
    if user.status.value != "ACTIVE":
        raise PermissionDeniedError("Account is not active")
    return user


async def get_current_member_read_only(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require a known member (ACTIVE or SUSPENDED).

    Suspended members can still log in and access read-only pages
    (browse tools, view own reservations, check notifications) so they
    can see their suspension notice and appeal information.
    """
    if user.status.value not in ("ACTIVE", "SUSPENDED"):
        raise PermissionDeniedError("Account status does not permit this action")
    return user


async def get_current_admin_user(
    user: Annotated[User, Depends(get_current_member)],
) -> User:
    """Require an active admin user."""
    if not user.is_admin:
        raise PermissionDeniedError("Admin access required")
    return user
