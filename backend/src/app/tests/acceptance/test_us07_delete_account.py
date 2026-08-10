"""User Story 7 — Delete Account.

Scenario numbering follows the doc exactly, including its gap: scenarios are
1, 2, 3, 5, 4 in document order (there is no missing "Scenario 4" between 3
and 5 -- the doc's own numbering jumps).
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReservationState, UserStatus
from app.tests.acceptance.helpers import auth_header
from app.tests.factories import ReservationFactory, ToolFactory, UserFactory

pytestmark = pytest.mark.acceptance


class TestScenario1DeleteWithNoActiveReservations:
    async def test_account_soft_deleted_and_pii_removed(
        self, client, db_session: AsyncSession
    ) -> None:
        user = await UserFactory.create_async(
            db_session,
            bio="my bio",
            neighborhood="Kaimuki",
            photo_url="https://example.com/p.jpg",
        )

        response = await client.delete("/api/v1/auth/me", headers=auth_header(user.id))
        assert response.status_code == 204

        await db_session.refresh(user)
        assert user.status == UserStatus.DELETED
        assert user.deleted_at is not None
        assert user.bio is None
        assert user.neighborhood is None
        assert user.photo_url is None
        assert user.email != "user+original@example.com"  # anonymized, not the real address


class TestScenario2ActiveReservationsBlockDeletion:
    async def test_active_reservation_as_borrower_blocks_deletion(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await ToolFactory.create_async(db_session, owner_id=owner.id)
        await ReservationFactory.create_async(
            db_session,
            tool_id=tool.id,
            borrower_id=borrower.id,
            state=ReservationState.APPROVED,
        )

        response = await client.delete("/api/v1/auth/me", headers=auth_header(borrower.id))
        assert response.status_code == 409
        assert "active reservations" in response.json()["detail"].lower()

    async def test_active_reservation_on_owned_listing_blocks_deletion(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await ToolFactory.create_async(db_session, owner_id=owner.id)
        await ReservationFactory.create_async(
            db_session,
            tool_id=tool.id,
            borrower_id=borrower.id,
            state=ReservationState.PICKED_UP,
        )

        response = await client.delete("/api/v1/auth/me", headers=auth_header(owner.id))
        assert response.status_code == 409


class TestScenario3ReservationHistoryIntegrityPreserved:
    async def test_display_name_is_preserved_after_deletion(
        self, client, db_session: AsyncSession
    ) -> None:
        user = await UserFactory.create_async(db_session, full_name="Taylor Reed")

        response = await client.delete("/api/v1/auth/me", headers=auth_header(user.id))
        assert response.status_code == 204

        await db_session.refresh(user)
        assert user.full_name == "Taylor Reed"


class TestScenario5SuspendedMemberCanStillDelete:
    async def test_suspended_member_can_delete_account(
        self, client, db_session: AsyncSession
    ) -> None:
        user = await UserFactory.create_async(db_session, status=UserStatus.SUSPENDED)

        response = await client.delete("/api/v1/auth/me", headers=auth_header(user.id))
        assert response.status_code == 204


class TestScenario4DeletedAccountCannotLogIn:
    async def test_login_after_deletion_is_rejected(self, client, db_session: AsyncSession) -> None:
        user = await UserFactory.create_async(db_session, email="us7-scenario4@example.com")

        delete_response = await client.delete("/api/v1/auth/me", headers=auth_header(user.id))
        assert delete_response.status_code == 204

        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "us7-scenario4@example.com",
                "password": "Password123!",  # pragma: allowlist secret
            },
        )
        assert login_response.status_code == 401


class TestScenario6DeletingOwnerCascadesToTheirListingsAndReservations:
    """Self-deletion is blocked outright if the member has an active
    reservation as borrower or a currently-PICKED_UP tool (Scenario 2), but
    a member who merely *owns* tools with pending REQUESTED/APPROVED
    reservations from *other* borrowers can still delete — those listings
    get deactivated and the pending reservations auto-cancelled with the
    affected borrowers notified.
    """

    async def test_active_listings_deactivated_pending_reservations_cancelled_borrowers_notified(
        self, client, db_session: AsyncSession
    ) -> None:
        from sqlalchemy import select

        from app.models.enums import NotificationType
        from app.models.notification import Notification

        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await ToolFactory.create_async(db_session, owner_id=owner.id, is_active=True)
        reservation = await ReservationFactory.create_async(
            db_session,
            tool_id=tool.id,
            borrower_id=borrower.id,
            state=ReservationState.REQUESTED,
        )

        response = await client.delete("/api/v1/auth/me", headers=auth_header(owner.id))
        assert response.status_code == 204

        await db_session.refresh(tool)
        assert tool.is_active is False

        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.CANCELLED

        notifications = (
            (
                await db_session.execute(
                    select(Notification).where(
                        Notification.user_id == borrower.id,
                        Notification.type == NotificationType.RESERVATION_CANCELLED.value,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(notifications) >= 1

    async def test_inactive_listings_are_left_alone(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        tool = await ToolFactory.create_async(db_session, owner_id=owner.id, is_active=False)

        response = await client.delete("/api/v1/auth/me", headers=auth_header(owner.id))
        assert response.status_code == 204

        await db_session.refresh(tool)
        assert tool.is_active is False
