"""User Story 30 — Admin Suspends a Member Account."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_audit_log import AdminAuditLog
from app.models.enums import DeactivationActor, ReservationState, UserStatus
from app.models.notification import Notification
from app.tests.acceptance.helpers import auth_header, make_admin
from app.tests.factories import ReservationFactory, ToolFactory, UserFactory

pytestmark = pytest.mark.acceptance


class TestScenario1AdminSuspendsMember:
    async def test_status_suspended_audit_logged_member_notified(
        self, client, db_session: AsyncSession
    ) -> None:
        admin = await make_admin(db_session)
        member = await UserFactory.create_async(db_session)

        response = await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "Repeated policy violations"},
            headers=auth_header(admin.id),
        )

        assert response.status_code == 200
        await db_session.refresh(member)
        assert member.status == UserStatus.SUSPENDED

        audit = (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.target_id == member.id,
                    AdminAuditLog.action_type == "USER_SUSPEND",
                )
            )
        ).scalar_one()
        assert audit.actor_id == admin.id
        assert audit.reason == "Repeated policy violations"

        notifications = (
            (
                await db_session.execute(
                    select(Notification).where(Notification.user_id == member.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(notifications) >= 1


class TestScenario2SuspendedMemberCannotUseRestrictedFeatures:
    async def test_suspended_member_blocked_from_creating_listing(
        self, client, db_session: AsyncSession
    ) -> None:
        admin = await make_admin(db_session)
        member = await UserFactory.create_async(db_session)
        await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "policy violation"},
            headers=auth_header(admin.id),
        )

        response = await client.post(
            "/api/v1/tools",
            data={"name": "Drill", "category": "POWER_TOOLS", "condition": "GOOD"},
            headers=auth_header(member.id),
        )
        assert response.status_code == 403

    async def test_suspended_member_can_still_browse_read_only(
        self, client, db_session: AsyncSession
    ) -> None:
        admin = await make_admin(db_session)
        member = await UserFactory.create_async(db_session)
        await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "policy violation"},
            headers=auth_header(admin.id),
        )

        response = await client.get("/api/v1/tools", headers=auth_header(member.id))
        assert response.status_code == 200


class TestScenario3SuspendedMemberCanStillLogIn:
    async def test_suspended_member_login_succeeds(self, client, db_session: AsyncSession) -> None:
        admin = await make_admin(db_session)
        member = await UserFactory.create_async(db_session, email="suspended-us30@example.com")
        await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "policy violation"},
            headers=auth_header(admin.id),
        )

        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "suspended-us30@example.com",
                "password": "Password123!",  # pragma: allowlist secret
            },
        )
        assert response.status_code == 200


class TestScenario4NonAdminCannotSuspendMember:
    async def test_returns_403_status_unchanged(self, client, db_session: AsyncSession) -> None:
        non_admin = await UserFactory.create_async(db_session)
        member = await UserFactory.create_async(db_session)

        response = await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "trying anyway"},
            headers=auth_header(non_admin.id),
        )

        assert response.status_code == 403
        await db_session.refresh(member)
        assert member.status == UserStatus.ACTIVE


class TestScenario5CannotSuspendAlreadySuspendedMember:
    async def test_rejected_with_conflict(self, client, db_session: AsyncSession) -> None:
        admin = await make_admin(db_session)
        member = await UserFactory.create_async(db_session)
        await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "first suspension"},
            headers=auth_header(admin.id),
        )

        response = await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "second attempt"},
            headers=auth_header(admin.id),
        )

        assert response.status_code == 409
        assert "already suspended" in response.json()["detail"].lower()


class TestScenario6SuspendedMembersToolListingsAreAutoDeactivated:
    async def test_active_listings_auto_deactivated_inactive_listings_unchanged(
        self, client, db_session: AsyncSession
    ) -> None:
        admin = await make_admin(db_session)
        member = await UserFactory.create_async(db_session)

        active_tool = await ToolFactory.create_async(db_session, owner_id=member.id, is_active=True)
        already_inactive_tool = await ToolFactory.create_async(
            db_session,
            owner_id=member.id,
            is_active=False,
            deactivated_by=DeactivationActor.OWNER,
            deactivated_at=datetime.now(UTC),
            deactivation_reason="manual hold",
        )

        response = await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "Repeated policy violations"},
            headers=auth_header(admin.id),
        )
        assert response.status_code == 200

        await db_session.refresh(active_tool)
        await db_session.refresh(already_inactive_tool)
        assert active_tool.is_active is False
        assert already_inactive_tool.is_active is False
        assert already_inactive_tool.deactivation_reason == "manual hold"


class TestScenario7SuspendedMembersPendingReservationsAreAutoCancelled:
    async def test_requested_and_approved_borrower_reservations_auto_cancelled(
        self, client, db_session: AsyncSession
    ) -> None:
        admin = await make_admin(db_session)
        member = await UserFactory.create_async(db_session)
        owner_one = await UserFactory.create_async(db_session)
        owner_two = await UserFactory.create_async(db_session)
        tool_one = await ToolFactory.create_async(db_session, owner_id=owner_one.id)
        tool_two = await ToolFactory.create_async(db_session, owner_id=owner_two.id)

        requested = await ReservationFactory.create_async(
            db_session,
            tool_id=tool_one.id,
            borrower_id=member.id,
            state=ReservationState.REQUESTED,
        )
        approved = await ReservationFactory.create_async(
            db_session,
            tool_id=tool_two.id,
            borrower_id=member.id,
            state=ReservationState.APPROVED,
        )

        response = await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "Repeated policy violations"},
            headers=auth_header(admin.id),
        )
        assert response.status_code == 200

        await db_session.refresh(requested)
        await db_session.refresh(approved)
        assert requested.state == ReservationState.CANCELLED
        assert approved.state == ReservationState.CANCELLED

        for owner in (owner_one, owner_two):
            notifications = (
                (
                    await db_session.execute(
                        select(Notification).where(Notification.user_id == owner.id)
                    )
                )
                .scalars()
                .all()
            )
            assert len(notifications) >= 1


class TestScenario8BorrowersWithReservationsOnSuspendedMembersToolsAreNotified:
    async def test_borrower_on_suspended_owners_tool_is_notified_and_freed(
        self, client, db_session: AsyncSession
    ) -> None:
        admin = await make_admin(db_session)
        member = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await ToolFactory.create_async(db_session, owner_id=member.id)
        reservation = await ReservationFactory.create_async(
            db_session,
            tool_id=tool.id,
            borrower_id=borrower.id,
            state=ReservationState.APPROVED,
        )

        response = await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "Repeated policy violations"},
            headers=auth_header(admin.id),
        )
        assert response.status_code == 200

        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.CANCELLED

        notifications = (
            (
                await db_session.execute(
                    select(Notification).where(Notification.user_id == borrower.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(notifications) >= 1


class TestScenario9SuspendingNonexistentMemberReturns404:
    async def test_returns_404(self, client, db_session: AsyncSession) -> None:
        import uuid

        admin = await make_admin(db_session)

        response = await client.post(
            f"/api/v1/admin/users/{uuid.uuid4()}/deactivate",
            json={"reason": "no such user"},
            headers=auth_header(admin.id),
        )
        assert response.status_code == 404


class TestScenario10CannotSuspendAnAlreadyDeletedAccount:
    async def test_returns_409(self, client, db_session: AsyncSession) -> None:
        admin = await make_admin(db_session)
        member = await UserFactory.create_async(db_session)

        delete_response = await client.request(
            "DELETE",
            f"/api/v1/admin/users/{member.id}",
            json={"reason": "test setup"},
            headers=auth_header(admin.id),
        )
        assert delete_response.status_code == 200

        response = await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "trying to suspend a deleted account"},
            headers=auth_header(admin.id),
        )
        assert response.status_code == 409
        assert "deleted" in response.json()["detail"].lower()
