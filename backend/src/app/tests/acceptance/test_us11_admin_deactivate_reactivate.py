"""User Story 11 — Deactivate and Reactivate Listings with Admin Controls."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReservationState
from app.models.notification import Notification
from app.tests.acceptance.helpers import auth_header, create_tool, make_admin
from app.tests.factories import ReservationFactory, UserFactory

pytestmark = pytest.mark.acceptance


class TestScenario1AdminDeactivatesActiveListing:
    async def test_listing_hidden_marked_deactivated_with_admin_and_timestamp(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        admin = await make_admin(db_session)
        tool = await create_tool(client, owner)

        response = await client.post(
            f"/api/v1/tools/{tool['id']}/deactivate",
            json={"reason": "reported as unsafe"},
            headers=auth_header(admin.id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False
        assert data["deactivated_by"] == "ADMIN"
        assert data["deactivated_at"] is not None

        other = await UserFactory.create_async(db_session)
        browse = await client.get("/api/v1/tools", headers=auth_header(other.id))
        assert not any(item["id"] == tool["id"] for item in browse.json()["items"])


class TestScenario2AdminCannotDeactivatePickedUpTool:
    async def test_deactivate_rejected_while_picked_up(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        admin = await make_admin(db_session)
        tool = await create_tool(client, owner)
        await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.PICKED_UP,
        )

        response = await client.post(
            f"/api/v1/tools/{tool['id']}/deactivate",
            json={"reason": "trying to deactivate mid-loan"},
            headers=auth_header(admin.id),
        )
        assert response.status_code == 409


class TestScenario3DeactivatingWithPendingReservationsAutoCancels:
    async def test_pending_reservations_auto_cancelled(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        admin = await make_admin(db_session)
        tool = await create_tool(client, owner)
        reservation = await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.APPROVED,
        )

        response = await client.post(
            f"/api/v1/tools/{tool['id']}/deactivate",
            json={"reason": "policy violation"},
            headers=auth_header(admin.id),
        )
        assert response.status_code == 200

        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.CANCELLED

    async def test_affected_borrower_is_notified(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        admin = await make_admin(db_session)
        tool = await create_tool(client, owner)
        await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.APPROVED,
        )

        await client.post(
            f"/api/v1/tools/{tool['id']}/deactivate",
            json={"reason": "policy violation"},
            headers=auth_header(admin.id),
        )

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


class TestScenario4AdminCanReactivateDeactivatedListing:
    async def test_listing_visible_again_owner_notified_audit_logged(
        self, client, db_session: AsyncSession
    ) -> None:
        from app.models.admin_audit_log import AdminAuditLog

        owner = await UserFactory.create_async(db_session)
        admin = await make_admin(db_session)
        tool = await create_tool(client, owner)
        await client.post(
            f"/api/v1/tools/{tool['id']}/deactivate",
            json={"reason": "temporary hold"},
            headers=auth_header(admin.id),
        )

        response = await client.post(
            f"/api/v1/tools/{tool['id']}/reactivate", headers=auth_header(admin.id)
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is True

        other = await UserFactory.create_async(db_session)
        browse = await client.get("/api/v1/tools", headers=auth_header(other.id))
        assert any(item["id"] == tool["id"] for item in browse.json()["items"])

        audit_rows = (
            (
                await db_session.execute(
                    select(AdminAuditLog).where(AdminAuditLog.actor_id == admin.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(audit_rows) >= 1

    async def test_owner_is_notified_of_reactivation(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        admin = await make_admin(db_session)
        tool = await create_tool(client, owner)
        await client.post(
            f"/api/v1/tools/{tool['id']}/deactivate",
            json={"reason": "temporary hold"},
            headers=auth_header(admin.id),
        )
        await client.post(f"/api/v1/tools/{tool['id']}/reactivate", headers=auth_header(admin.id))

        notifications = (
            (await db_session.execute(select(Notification).where(Notification.user_id == owner.id)))
            .scalars()
            .all()
        )
        assert len(notifications) >= 1


class TestScenario5DeactivationLoggedWithAdminIdTimestampReason:
    async def test_audit_log_entry_has_admin_listing_reason(
        self, client, db_session: AsyncSession
    ) -> None:
        from app.models.admin_audit_log import AdminAuditLog

        owner = await UserFactory.create_async(db_session)
        admin = await make_admin(db_session)
        tool = await create_tool(client, owner)

        await client.post(
            f"/api/v1/tools/{tool['id']}/deactivate",
            json={"reason": "does not meet safety standards"},
            headers=auth_header(admin.id),
        )

        entry = (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.actor_id == admin.id)
            )
        ).scalar_one()
        assert entry.reason == "does not meet safety standards"
        assert entry.target_id == uuid.UUID(tool["id"])
        assert entry.created_at is not None

    async def test_audit_log_is_filterable_by_date_and_listing(
        self, client, db_session: AsyncSession
    ) -> None:
        """GET /admin/audit-log supports target_id (listing) and date-range
        filters; filtering by the acting admin is covered separately in
        test_audit_log_filterable_by_acting_admin below."""
        owner = await UserFactory.create_async(db_session)
        admin = await make_admin(db_session)
        tool_a = await create_tool(client, owner, name="Tool A")
        tool_b = await create_tool(client, owner, name="Tool B")

        await client.post(
            f"/api/v1/tools/{tool_a['id']}/deactivate",
            json={"reason": "reason A"},
            headers=auth_header(admin.id),
        )
        await client.post(
            f"/api/v1/tools/{tool_b['id']}/deactivate",
            json={"reason": "reason B"},
            headers=auth_header(admin.id),
        )

        by_listing = await client.get(
            "/api/v1/admin/audit-log",
            params={"target_id": tool_a["id"]},
            headers=auth_header(admin.id),
        )
        assert by_listing.status_code == 200
        listing_items = by_listing.json()["items"]
        assert len(listing_items) == 1
        assert listing_items[0]["target_id"] == tool_a["id"]

        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        by_date = await client.get(
            "/api/v1/admin/audit-log",
            params={"date_from": future},
            headers=auth_header(admin.id),
        )
        assert by_date.status_code == 200
        assert by_date.json()["items"] == []

    async def test_audit_log_filterable_by_acting_admin(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        admin_one = await make_admin(db_session)
        admin_two = await make_admin(db_session)
        tool_a = await create_tool(client, owner, name="Tool A")
        tool_b = await create_tool(client, owner, name="Tool B")

        await client.post(
            f"/api/v1/tools/{tool_a['id']}/deactivate",
            json={"reason": "reason A"},
            headers=auth_header(admin_one.id),
        )
        await client.post(
            f"/api/v1/tools/{tool_b['id']}/deactivate",
            json={"reason": "reason B"},
            headers=auth_header(admin_two.id),
        )

        response = await client.get(
            "/api/v1/admin/audit-log",
            params={"actor_id": str(admin_one.id)},
            headers=auth_header(admin_one.id),
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["actor_id"] == str(admin_one.id)


class TestScenario6DeactivatedListingStillViewableByInsiders:
    async def test_owner_admin_and_participant_can_view_deactivated_listing(
        self, client, db_session: AsyncSession
    ) -> None:
        """GET /tools/{id} must not 404 for insiders of a deactivated listing.

        The owner, an admin, and any member with a reservation on the tool
        (past reservation history / message threads) can still view it,
        showing the deactivated state and date. Unrelated members get 404.
        """
        owner = await UserFactory.create_async(db_session)
        admin = await make_admin(db_session)
        borrower = await UserFactory.create_async(db_session)
        other = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)
        await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.APPROVED,
        )
        await client.post(
            f"/api/v1/tools/{tool['id']}/deactivate",
            json={"reason": "temporary hold"},
            headers=auth_header(admin.id),
        )

        # Owner sees it as deactivated with the date.
        response = await client.get(f"/api/v1/tools/{tool['id']}", headers=auth_header(owner.id))
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False
        assert data["deactivated_at"] is not None
        assert data["deactivated_by"] == "ADMIN"

        # Admin can view it.
        response = await client.get(f"/api/v1/tools/{tool['id']}", headers=auth_header(admin.id))
        assert response.status_code == 200
        assert response.json()["is_active"] is False

        # Borrower with a reservation can still view it.
        response = await client.get(f"/api/v1/tools/{tool['id']}", headers=auth_header(borrower.id))
        assert response.status_code == 200

        # Unrelated member still gets 404.
        response = await client.get(f"/api/v1/tools/{tool['id']}", headers=auth_header(other.id))
        assert response.status_code == 404
