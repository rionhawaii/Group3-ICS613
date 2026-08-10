"""Authentication service."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    ValidationError,
    VerifyTokenError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.email_verification import EmailVerificationToken
from app.models.enums import InviteStatus, UserStatus
from app.models.invite import InviteToken
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services.email import EmailService
from app.services.user import UserService

DEFAULT_TOKEN_TTL_HOURS = 24
INVITE_TTL_DAYS = 7
PASSWORD_RESET_TTL_HOURS = 1


def _now() -> datetime:
    return datetime.now(UTC)


class AuthService:
    """All authentication and identity lifecycle operations."""

    def __init__(self, email_service: EmailService | None = None) -> None:
        self.email_service = email_service or EmailService()

    # ------------------------------------------------------------------
    # Admin invite
    # ------------------------------------------------------------------
    async def create_invite(
        self,
        db: AsyncSession,
        *,
        email: str,
        admin_user: User,
    ) -> InviteToken:
        """Create an invite token for a new member email address."""
        normalized_email = email.lower().strip()

        existing_user = await UserService().get_by_email(db, normalized_email)
        if existing_user is not None:
            raise ConflictError("An account with this email already exists")

        token = InviteToken(
            email=normalized_email,
            created_by=admin_user.id,
            status=InviteStatus.SENT,
            expires_at=_now() + timedelta(days=INVITE_TTL_DAYS),
        )
        db.add(token)
        await db.flush()
        await db.refresh(token)

        self.email_service.send_invite_email(token.email, token.token)
        return token

    async def list_invites(self, db: AsyncSession) -> list[InviteToken]:
        """List all invite tokens, newest first (admin-only)."""
        result = await db.execute(select(InviteToken).order_by(InviteToken.created_at.desc()))
        return list(result.scalars().all())

    async def revoke_invite(
        self,
        db: AsyncSession,
        *,
        invite_id: uuid.UUID,
        admin_user: User,
    ) -> InviteToken:
        """Revoke a SENT invite token so it can no longer be used.

        Only SENT invites can be revoked. Already USED, EXPIRED, or
        REVOKED invites raise an appropriate error.
        """
        result = await db.execute(select(InviteToken).where(InviteToken.id == invite_id))
        invite = result.scalar_one_or_none()
        if invite is None:
            from app.core.exceptions import NotFoundError

            raise NotFoundError("Invite not found")

        if invite.status == InviteStatus.REVOKED:
            raise ConflictError("Invite is already revoked")
        if invite.status == InviteStatus.USED:
            raise ConflictError("Invite has already been used and cannot be revoked")
        if invite.status == InviteStatus.EXPIRED:
            raise ConflictError("Invite has already expired")

        invite.status = InviteStatus.REVOKED
        db.add(invite)
        await db.flush()
        await db.refresh(invite)
        return invite

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    async def register(
        self,
        db: AsyncSession,
        *,
        email: str,
        password: str,
        full_name: str | None,
        invite_token_str: str,
    ) -> User:
        """Register a new user with a valid invite token."""
        normalized_email = email.lower().strip()

        result = await db.execute(
            select(InviteToken).where(
                InviteToken.token == invite_token_str,
                InviteToken.email == normalized_email,
                InviteToken.status == InviteStatus.SENT,
                InviteToken.expires_at > _now(),
            )
        )
        invite = result.scalar_one_or_none()
        if invite is None:
            raise ValidationError("Invalid or expired invite token")

        existing_user = await UserService().get_by_email(db, normalized_email)
        if existing_user is not None:
            raise ConflictError("An account with this email already exists")

        user = User(
            email=normalized_email,
            hashed_password=hash_password(password),
            full_name=full_name.strip() if full_name else None,
            status=UserStatus.EMAIL_PENDING,
            is_admin=False,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

        invite.status = InviteStatus.USED
        invite.used_at = _now()
        db.add(invite)

        verification_token = EmailVerificationToken(
            user_id=user.id,
            expires_at=_now() + timedelta(hours=DEFAULT_TOKEN_TTL_HOURS),
        )
        db.add(verification_token)
        await db.flush()

        self.email_service.send_verification_email(user.email, verification_token.token)
        return user

    # ------------------------------------------------------------------
    # Email verification
    # ------------------------------------------------------------------
    async def verify_email(
        self,
        db: AsyncSession,
        *,
        token_str: str,
    ) -> dict[str, str]:
        """Verify a user's email and return a token pair."""
        result = await db.execute(
            select(EmailVerificationToken)
            .where(EmailVerificationToken.token == token_str)
            .options(selectinload(EmailVerificationToken.user))
        )
        token = result.scalar_one_or_none()

        if token is None:
            raise VerifyTokenError("Invalid verification token", resend_available=True)
        if token.used_at is not None:
            raise VerifyTokenError("Token already used", resend_available=False)
        if token.expires_at < _now():
            raise VerifyTokenError("Verification token expired", resend_available=True)

        user = token.user
        if user.status != UserStatus.EMAIL_PENDING:
            raise VerifyTokenError("Email already verified", resend_available=False)

        user.status = UserStatus.ACTIVE
        user.updated_at = _now()
        token.used_at = _now()
        db.add(user)
        db.add(token)
        await db.flush()

        return {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
        }

    async def resend_verification(
        self,
        db: AsyncSession,
        *,
        email: str,
    ) -> None:
        """Resend a verification email. Always returns silently."""
        normalized_email = email.lower().strip()
        user = await UserService().get_by_email(db, normalized_email)

        if user is None or user.status != UserStatus.EMAIL_PENDING or user.deleted_at is not None:
            return

        # Mark any existing pending tokens as expired.
        await db.execute(
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.expires_at > _now(),
            )
            .values(expires_at=_now())
        )

        new_token = EmailVerificationToken(
            user_id=user.id,
            expires_at=_now() + timedelta(hours=DEFAULT_TOKEN_TTL_HOURS),
        )
        db.add(new_token)
        await db.flush()

        self.email_service.send_verification_email(user.email, new_token.token)

    # ------------------------------------------------------------------
    # Login / logout / refresh
    # ------------------------------------------------------------------
    async def login(
        self,
        db: AsyncSession,
        *,
        email: str,
        password: str,
    ) -> dict[str, str]:
        """Authenticate a user and return a token pair.

        The endpoint always returns the same generic error message
        ("Invalid email or password") on any failure, regardless of the
        underlying reason (unknown email, wrong password, unverified email,
        suspended account). This prevents email enumeration by an attacker
        who probes the endpoint to learn which addresses are registered.

        Users with a valid email but a status issue (unverified, suspended)
        can use the dedicated ``/auth/resend-verification`` and the
        "contact admin" flow respectively — they don't need the error
        message to be specific to know there's a problem.
        """
        normalized_email = email.lower().strip()
        user = await UserService().get_by_email(db, normalized_email)

        # All failure paths return the same opaque message. Order matters only
        # for the bcrypt verify step (don't run it for unknown emails —
        # both to avoid timing leaks and to keep the error mapping identical).
        # ``get_by_email`` now filters out soft-deleted users, so a non-None
        # result here is always an active or status-pending user.
        if user is None:
            raise AuthenticationError("Invalid email or password")

        # SUSPENDED users may log in so they can see a suspension notice.
        # EMAIL_PENDING and DELETED users cannot authenticate.
        if user.status == UserStatus.EMAIL_PENDING:
            raise AuthenticationError("Invalid email or password")
        if user.status not in (UserStatus.ACTIVE, UserStatus.SUSPENDED):
            raise AuthenticationError("Invalid email or password")
        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")

        return {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
        }

    async def refresh(
        self,
        db: AsyncSession,
        *,
        refresh_token_str: str,
    ) -> dict[str, str]:
        """Rotate a refresh token into a new access/refresh pair.

        Rejects tokens issued before the user's password was changed, so
        a password reset (or any future password change) invalidates every
        existing refresh token — matching the access-token rejection in
        get_current_user (dependencies.py).
        """
        payload = decode_token(refresh_token_str)
        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")

        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid token subject")

        user = await UserService().get_by_id(db, uuid.UUID(user_id))
        if user is None or user.deleted_at is not None:
            raise AuthenticationError("User not found")
        if user.status == UserStatus.EMAIL_PENDING:
            raise AuthenticationError("Account is not active")
        if user.status not in (UserStatus.ACTIVE, UserStatus.SUSPENDED):
            raise AuthenticationError("Account is not active")

        # Reject refresh tokens issued before the password was last changed.
        # This mirrors the access-token check in get_current_user and ensures
        # that a password reset invalidates EVERY existing session, not just
        # the access tokens.
        if user.password_changed_at is not None:
            token_iat = payload.get("iat")
            if token_iat is not None:
                token_issued = datetime.fromtimestamp(token_iat, UTC)
                if token_issued < user.password_changed_at:
                    raise AuthenticationError("Token issued before password change")

        return {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
        }

    async def logout(self, db: AsyncSession, user: User) -> None:
        """Stateless logout.

        The JWT itself remains technically valid until it expires (the client
        should discard it). A future Redis-backed JTI deny-list can plug
        in here to invalidate access tokens before their natural expiry
        without changing this signature.
        """
        # No-op: clients are expected to drop the token. We deliberately
        # avoid touching ``password_changed_at`` here because that would
        # log every active user out (e.g. from multiple devices) on each
        # logout. Use a JTI deny-list if/when immediate revocation is
        # required.
        return None

    # ------------------------------------------------------------------
    # Password reset
    # ------------------------------------------------------------------
    async def forgot_password(
        self,
        db: AsyncSession,
        *,
        email: str,
    ) -> None:
        """Send a password reset email if the account exists."""
        normalized_email = email.lower().strip()
        user = await UserService().get_by_email(db, normalized_email)

        if user is None or user.deleted_at is not None:
            return

        # Invalidate existing unused tokens.
        await db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > _now(),
            )
            .values(expires_at=_now())
        )

        reset_token = PasswordResetToken(
            user_id=user.id,
            expires_at=_now() + timedelta(hours=PASSWORD_RESET_TTL_HOURS),
        )
        db.add(reset_token)
        await db.flush()

        self.email_service.send_password_reset_email(user.email, reset_token.token)

    async def reset_password(
        self,
        db: AsyncSession,
        *,
        token_str: str,
        new_password: str,
    ) -> dict[str, str]:
        """Consume a password reset token and set a new password."""
        result = await db.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.token == token_str)
            .options(selectinload(PasswordResetToken.user))
        )
        token = result.scalar_one_or_none()

        if token is None:
            raise ValidationError("Invalid reset token")
        if token.used_at is not None:
            raise ValidationError("Reset token already used")
        if token.expires_at < _now():
            raise ValidationError("Reset token expired")

        user = token.user
        user.hashed_password = hash_password(new_password)
        user.password_changed_at = _now()
        user.updated_at = _now()
        token.used_at = _now()
        db.add(user)
        db.add(token)
        await db.flush()

        return {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
        }

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------
    async def get_me(self, db: AsyncSession, user: User) -> User:
        """Return the current user."""
        return user

    async def update_me(
        self,
        db: AsyncSession,
        user: User,
        *,
        updates: dict[str, str | None],
    ) -> User:
        """Update the current user's profile.

        ``updates`` contains only fields the client explicitly submitted;
        ``None`` values clear the corresponding field.
        """
        return await UserService().update_profile(db, user, updates=updates)

    async def upload_profile_photo(
        self,
        db: AsyncSession,
        user: User,
        *,
        file: UploadFile,
    ) -> User:
        """Validate and attach an uploaded profile photo to the current user."""
        return await UserService().upload_profile_photo(db, user, file=file)

    async def delete_me(
        self,
        db: AsyncSession,
        user: User,
    ) -> None:
        """Soft-delete the current user's account.

        R1.A: no reservation check yet (Reservation model is added in R1.B).
        R1.B will add an active-reservation guard before soft deletion.
        """
        await UserService().soft_delete(db, user)
