"""Admin service — moderation actions with audit logging."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models.admin_audit_log import AdminAuditLog
from app.models.enums import CancellerType, NotificationType, ReservationState, UserStatus
from app.models.reservation import Reservation
from app.models.tool import Tool
from app.models.user import User
from app.services.notification import NotificationService
from app.services.user import _anonymize_user, _guard_and_cleanup


class AdminService:
    """Moderation actions performed by admins. Every action is audited."""

    # ------------------------------------------------------------------
    # User listing (admin dashboard)
    # ------------------------------------------------------------------
    async def get_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> User:
        """Fetch a single non-deleted user by ID. Raises 404 if not found."""
        result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def list_users(
        self,
        db: AsyncSession,
        *,
        status: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[User], int]:
        """List all non-deleted users with optional filters.

        Admins can filter by status (ACTIVE, SUSPENDED, EMAIL_PENDING) and
        search by email or full_name.
        """
        query = select(User).where(User.deleted_at.is_(None))
        count_q = select(func.count(User.id)).where(User.deleted_at.is_(None))

        if status:
            try:
                status_enum = UserStatus(status.upper())
                query = query.where(User.status == status_enum)
                count_q = count_q.where(User.status == status_enum)
            except ValueError:
                pass

        if search:
            pattern = f"%{search.strip()}%"
            query = query.where(User.email.ilike(pattern) | User.full_name.ilike(pattern))
            count_q = count_q.where(User.email.ilike(pattern) | User.full_name.ilike(pattern))

        count_result = await db.execute(count_q)
        total = count_result.scalar() or 0

        query = (
            query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        result = await db.execute(query)
        users = list(result.scalars().all())

        return users, total

    # ------------------------------------------------------------------
    # User management
    # ------------------------------------------------------------------
    async def deactivate_user(
        self,
        db: AsyncSession,
        *,
        admin: User,
        target_user_id: uuid.UUID,
        reason: str,
    ) -> User:
        """Admin deactivates (suspends) a member account.

        Refuses to suspend:
          - the admin themselves
          - any other admin (prevents lock-out of the moderation team)
        """
        if not admin.is_admin:
            raise PermissionDeniedError("Admin access required")

        target = await db.get(User, target_user_id)
        if target is None:
            raise NotFoundError("User not found")
        if target.id == admin.id:
            raise ConflictError("Cannot suspend yourself")
        if target.is_admin:
            raise ConflictError("Cannot suspend another admin")
        if target.status == UserStatus.SUSPENDED:
            raise ConflictError("User is already suspended")
        if target.status == UserStatus.DELETED:
            raise ConflictError("Cannot suspend a deleted account")

        target.status = UserStatus.SUSPENDED
        target.updated_at = datetime.now(UTC)
        db.add(target)

        await self._audit(
            db,
            actor_id=admin.id,
            action_type="USER_SUSPEND",
            target_type="user",
            target_id=target.id,
            reason=reason,
        )

        # Notify the affected user (best-effort; no fail if notification fails)
        await NotificationService().create(
            db,
            user_id=target.id,
            type_=NotificationType.ACCOUNT_SUSPENDED,
            title="Account suspended",
            body=f"Your account was suspended. Reason: {reason}",
            payload={"actor_id": str(admin.id)},
        )

        # Local import: tool.py imports AdminService at module level, so a
        # module-level import here would create a circular import.
        from app.services.tool import ToolService

        # Owner-side cascade: deactivate the suspended member's active tool
        # listings, notifying any borrowers whose pending reservations get
        # auto-cancelled as a result. Tools currently PICKED_UP are skipped
        # (not force-returned) -- see FIX_PLAN_serious_issues.local.md FIX 2.
        owned_tools = await db.execute(
            select(Tool).where(
                Tool.owner_id == target.id,
                Tool.is_active.is_(True),
                Tool.deleted_at.is_(None),
            )
        )
        for tool in owned_tools.scalars().all():
            affected = (
                (
                    await db.execute(
                        select(Reservation).where(
                            Reservation.tool_id == tool.id,
                            Reservation.state.in_(
                                [ReservationState.REQUESTED, ReservationState.APPROVED]
                            ),
                        )
                    )
                )
                .scalars()
                .all()
            )
            try:
                await ToolService().deactivate_tool(
                    db,
                    tool=tool,
                    actor=admin,
                    reason=f"Owner account suspended: {reason}",
                )
            except ConflictError:
                continue

            for r in affected:
                await NotificationService().create(
                    db,
                    user_id=r.borrower_id,
                    type_=NotificationType.RESERVATION_CANCELLED,
                    title="Reservation cancelled",
                    body="Your reservation was cancelled because the tool owner's "
                    "account was suspended.",
                    payload={"reservation_id": str(r.id), "reason": "owner_account_suspended"},
                )

        # Borrower-side cascade: cancel the suspended member's own pending
        # reservations and notify the affected tool owners.
        now = datetime.now(UTC)
        borrower_reservations = (
            (
                await db.execute(
                    select(Reservation).where(
                        Reservation.borrower_id == target.id,
                        Reservation.state.in_(
                            [ReservationState.REQUESTED, ReservationState.APPROVED]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for r in borrower_reservations:
            r.state = ReservationState.CANCELLED
            r.cancelled_by_type = CancellerType.SYSTEM.value
            r.cancelled_reason = f"Borrower account suspended: {reason}"
            r.updated_at = now
            db.add(r)

            await NotificationService().create(
                db,
                user_id=r.tool.owner_id,
                type_=NotificationType.RESERVATION_CANCELLED,
                title="Reservation cancelled",
                body="A reservation on your tool was cancelled because the "
                "borrower's account was suspended.",
                payload={"reservation_id": str(r.id), "reason": "borrower_account_suspended"},
            )

        await db.flush()
        return target

    async def reactivate_user(
        self,
        db: AsyncSession,
        *,
        admin: User,
        target_user_id: uuid.UUID,
        reason: str = "Admin reactivation",
    ) -> User:
        """Admin reactivates a suspended member."""
        if not admin.is_admin:
            raise PermissionDeniedError("Admin access required")

        target = await db.get(User, target_user_id)
        if target is None:
            raise NotFoundError("User not found")
        if target.status != UserStatus.SUSPENDED:
            raise ConflictError("User is not suspended")

        target.status = UserStatus.ACTIVE
        target.updated_at = datetime.now(UTC)
        db.add(target)

        await self._audit(
            db,
            actor_id=admin.id,
            action_type="USER_REACTIVATE",
            target_type="user",
            target_id=target.id,
            reason=reason,
        )

        await NotificationService().create(
            db,
            user_id=target.id,
            type_=NotificationType.ACCOUNT_REACTIVATED,
            title="Account reactivated",
            body="Your account has been reactivated by an admin.",
            payload={"actor_id": str(admin.id)},
        )

        await db.flush()
        return target

    async def delete_user(
        self,
        db: AsyncSession,
        *,
        admin: User,
        target_user_id: uuid.UUID,
        reason: str,
    ) -> None:
        """Admin hard-deletes a user account (anonymizes PII, marks DELETED).

        Same protections as ``deactivate_user``: refuses to delete the admin
        themselves or any other admin. Soft-deleted users (DELETED status)
        can be re-targeted to overwrite their PII again if needed.

        Uses the shared ``_guard_and_cleanup`` from ``app.services.user``
        to deactivate tools and cancel pending reservations — no duplicated
        logic between self-service and admin deletion.
        """
        if not admin.is_admin:
            raise PermissionDeniedError("Admin access required")

        target = await db.get(User, target_user_id)
        if target is None:
            raise NotFoundError("User not found")
        if target.id == admin.id:
            raise ConflictError("Cannot delete yourself")
        if target.is_admin:
            raise ConflictError("Cannot delete another admin")

        # Shared guard + tool deactivation / reservation cancellation.
        cleanup = await _guard_and_cleanup(db, target)

        await self._audit(
            db,
            actor_id=admin.id,
            action_type="ACCOUNT_DELETE",
            target_type="user",
            target_id=target.id,
            reason=reason,
            metadata_={
                "tools_deactivated": cleanup.tools_deactivated,
                "reservations_cancelled": cleanup.reservations_cancelled,
            },
        )

        _anonymize_user(target)
        target.status = UserStatus.DELETED
        target.deleted_at = datetime.now(UTC)
        target.updated_at = datetime.now(UTC)
        db.add(target)
        await db.flush()

    # ------------------------------------------------------------------
    # Tool moderation (R1.C audit log coverage)
    # ------------------------------------------------------------------
    async def record_tool_deactivation(
        self,
        db: AsyncSession,
        *,
        actor: User,
        tool_id: uuid.UUID,
        reason: str,
        actor_role: str,
    ) -> AdminAuditLog:
        """Audit-log a tool deactivation (owner or admin)."""
        return await self._audit(
            db,
            actor_id=actor.id,
            action_type="TOOL_DEACTIVATED",
            target_type="tool",
            target_id=tool_id,
            reason=reason,
            metadata_={"actor_role": actor_role},
        )

    async def record_tool_reactivation(
        self,
        db: AsyncSession,
        *,
        admin: User,
        tool_id: uuid.UUID,
    ) -> AdminAuditLog:
        """Audit-log a tool reactivation (admin only)."""
        return await self._audit(
            db,
            actor_id=admin.id,
            action_type="TOOL_REACTIVATED",
            target_type="tool",
            target_id=tool_id,
            reason="Admin reactivation",
            metadata_={"actor_role": "admin"},
        )

    async def record_reservation_force_return(
        self,
        db: AsyncSession,
        *,
        admin: User,
        reservation_id: uuid.UUID,
        reason: str,
        tool_id: uuid.UUID,
    ) -> AdminAuditLog:
        """Audit-log an admin force-return of a reservation."""
        return await self._audit(
            db,
            actor_id=admin.id,
            action_type="RESERVATION_FORCE_RETURN",
            target_type="reservation",
            target_id=reservation_id,
            reason=reason,
            metadata_={"tool_id": str(tool_id)},
        )

    # ------------------------------------------------------------------
    # Admin reservation overview (US34)
    # ------------------------------------------------------------------
    async def list_all_reservations(
        self,
        db: AsyncSession,
        *,
        state: str | None = None,
        member_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Reservation], int]:
        """Admin-only: list all reservations with filters (US34).

        Filters:
          - state: filter by reservation state
          - member_id: filter by borrower_id or tool owner_id
          - date_from / date_to: filter by reservation start_date range
        """
        query = select(Reservation)
        count_q = select(func.count(Reservation.id))

        if state:
            try:
                state_enum = ReservationState(state.upper())
                query = query.where(Reservation.state == state_enum)
                count_q = count_q.where(Reservation.state == state_enum)
            except ValueError:
                pass

        if member_id is not None:
            # Match borrower or owner (via tool subquery)
            query = query.where(
                or_(
                    Reservation.borrower_id == member_id,
                    Reservation.tool_id.in_(select(Tool.id).where(Tool.owner_id == member_id)),
                )
            )
            count_q = count_q.where(
                or_(
                    Reservation.borrower_id == member_id,
                    Reservation.tool_id.in_(select(Tool.id).where(Tool.owner_id == member_id)),
                )
            )

        if date_from is not None:
            query = query.where(Reservation.start_date >= date_from)
            count_q = count_q.where(Reservation.start_date >= date_from)
        if date_to is not None:
            query = query.where(Reservation.start_date <= date_to)
            count_q = count_q.where(Reservation.start_date <= date_to)

        total = (await db.execute(count_q)).scalar() or 0

        query = (
            query.options(
                selectinload(Reservation.tool).selectinload(Tool.owner),
                selectinload(Reservation.borrower),
            )
            .order_by(Reservation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(query)
        reservations = list(result.scalars().unique())

        return reservations, total

    # ------------------------------------------------------------------
    # Audit log queries
    # ------------------------------------------------------------------
    async def list_audit_log(
        self,
        db: AsyncSession,
        *,
        actor_id: uuid.UUID | None = None,
        action_type: str | None = None,
        target_type: str | None = None,
        target_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AdminAuditLog], int]:
        """Query the admin audit log with optional filters (US32).

        Supports filtering by actor_id (which admin performed the action),
        action_type, target_type, target_id, and a date range (date_from /
        date_to, inclusive on date_to).
        """
        query = select(AdminAuditLog)
        count_q = select(func.count(AdminAuditLog.id))

        if actor_id is not None:
            query = query.where(AdminAuditLog.actor_id == actor_id)
            count_q = count_q.where(AdminAuditLog.actor_id == actor_id)
        if action_type:
            query = query.where(AdminAuditLog.action_type == action_type)
            count_q = count_q.where(AdminAuditLog.action_type == action_type)
        if target_type:
            query = query.where(AdminAuditLog.target_type == target_type)
            count_q = count_q.where(AdminAuditLog.target_type == target_type)
        if target_id is not None:
            query = query.where(AdminAuditLog.target_id == target_id)
            count_q = count_q.where(AdminAuditLog.target_id == target_id)
        if date_from is not None:
            query = query.where(AdminAuditLog.created_at >= date_from)
            count_q = count_q.where(AdminAuditLog.created_at >= date_from)
        if date_to is not None:
            query = query.where(AdminAuditLog.created_at <= date_to)
            count_q = count_q.where(AdminAuditLog.created_at <= date_to)

        count_result = await db.execute(count_q)
        total = count_result.scalar() or 0

        query = (
            query.order_by(AdminAuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(query)
        entries = list(result.scalars().all())

        return entries, total

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _audit(
        self,
        db: AsyncSession,
        *,
        actor_id: uuid.UUID,
        action_type: str,
        target_type: str,
        target_id: uuid.UUID,
        reason: str,
        metadata_: dict | None = None,
    ) -> AdminAuditLog:
        """Insert an immutable audit log entry."""
        entry = AdminAuditLog(
            actor_id=actor_id,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            metadata_=metadata_,
        )
        db.add(entry)
        return entry
