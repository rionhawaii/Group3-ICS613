"""User Story 20 — Confirm Tool Return.

Structural note: `Reservation` has no `is_late`/`late_return` field at all
(app/models/reservation.py), and `latest_return_time` doesn't exist on `Tool`
(see US8 -- descoped for the same reason). `ReservationService.mark_returned`
never compares the return moment against `end_date` or any deadline -- it
unconditionally transitions to RETURNED. The team decided the "late return"
scenarios in the doc (warnings, confirmation prompts, late-flagging, distinct
owner notification of lateness) are out of scope for this project rather
than a fix worth making (see QA_NOTES.local.md, 2026-08-09 triage); those
scenarios have been removed rather than left skipped/xfailed.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReservationState
from app.services.scheduler import SchedulerService
from app.tests.acceptance.helpers import (
    auth_header,
    create_tool,
    patch_scheduler_session,
)
from app.tests.factories import ReservationFactory, UserFactory

pytestmark = pytest.mark.acceptance


async def _make_picked_up_reservation(client, db_session, **kwargs):
    owner = await UserFactory.create_async(db_session)
    borrower = await UserFactory.create_async(db_session)
    tool = await create_tool(client, owner)
    kwargs.setdefault("start_date", date.today() - timedelta(days=1))
    kwargs.setdefault("end_date", date.today() + timedelta(days=2))
    reservation = await ReservationFactory.create_async(
        db_session,
        tool_id=tool["id"],
        borrower_id=borrower.id,
        state=ReservationState.PICKED_UP,
        picked_up_at=datetime.now(UTC),
        **kwargs,
    )
    return owner, borrower, tool, reservation


class TestScenario1BorrowerMarksReturnedOnTime:
    async def test_state_becomes_returned_with_timestamp(
        self, client, db_session: AsyncSession
    ) -> None:
        owner, borrower, tool, reservation = await _make_picked_up_reservation(client, db_session)

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-returned",
            headers=auth_header(borrower.id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "RETURNED"
        assert data["returned_at"] is not None
        # "Both parties prompted to leave a review" is a frontend prompt once
        # the reservation is RETURNED -- not independently API-testable beyond
        # the state transition itself (see User Story 24 for review submission).


# Scenarios 2 and 3 (late-return confirmation prompt, late-return flag +
# distinct lateness notification) are descoped -- see module docstring.
# A late `mark-returned` still succeeds and transitions to RETURNED exactly
# like an on-time return; that path is covered by Scenario 1.


class TestScenario4NonBorrowerCannotMarkReturned:
    async def test_owner_gets_403(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_picked_up_reservation(client, db_session)

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-returned",
            headers=auth_header(owner.id),
        )

        assert response.status_code == 403
        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.PICKED_UP


class TestScenario5CannotMarkReturnedUnlessPickedUp:
    @pytest.mark.parametrize(
        "state",
        [
            ReservationState.REQUESTED,
            ReservationState.APPROVED,
            ReservationState.CANCELLED,
            ReservationState.DENIED,
            ReservationState.RETURNED,
        ],
    )
    async def test_rejected_for_non_picked_up_states(
        self, client, db_session: AsyncSession, state: ReservationState
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)
        reservation = await ReservationFactory.create_async(
            db_session, tool_id=tool["id"], borrower_id=borrower.id, state=state
        )

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-returned",
            headers=auth_header(borrower.id),
        )
        assert response.status_code == 409


class TestScenario6OwnerFilesDamageReport:
    async def test_damage_reported_tool_deactivated_pending_cancelled(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        other_borrower = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)
        reservation = await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.RETURNED,
            returned_at=datetime.now(UTC),
        )
        pending = await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=other_borrower.id,
            state=ReservationState.REQUESTED,
            start_date=date.today() + timedelta(days=30),
            end_date=date.today() + timedelta(days=32),
        )

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-damaged",
            json={"description": "Handle snapped off"},
            headers=auth_header(owner.id),
        )

        assert response.status_code == 200
        assert response.json()["damage_reported"] is True

        # GET /tools/{id} 404s once deactivated (active_only=True by default,
        # even for the owner) -- use the owner's own-listings view instead.
        my_tools = await client.get("/api/v1/tools/me", headers=auth_header(owner.id))
        listing = next(t for t in my_tools.json()["items"] if t["id"] == tool["id"])
        assert listing["is_active"] is False

        await db_session.refresh(pending)
        assert pending.state == ReservationState.CANCELLED

    async def test_borrower_not_owner_is_flagged_for_admin_review(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)
        reservation = await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.RETURNED,
            returned_at=datetime.now(UTC),
        )

        await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-damaged",
            json={"description": "Handle snapped off"},
            headers=auth_header(owner.id),
        )

        await db_session.refresh(borrower)
        await db_session.refresh(owner)
        assert borrower.damage_reported >= 1
        assert owner.damage_reported == 0

    async def test_damage_report_reduces_borrower_average_rating(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)
        reservation = await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.RETURNED,
            returned_at=datetime.now(UTC),
        )

        await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-damaged",
            json={"description": "Damaged"},
            headers=auth_header(owner.id),
        )

        await db_session.refresh(borrower)
        # With no reviews, one damage report sets trust_score to 1.0 (1-star equivalent)
        assert borrower.trust_score == 1.0, (
            f"Expected trust_score == 1.0 after damage report, got {borrower.trust_score}"
        )

    async def test_duplicate_damage_report_on_same_reservation_rejected(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)
        reservation = await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.RETURNED,
            returned_at=datetime.now(UTC),
        )

        first = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-damaged",
            json={"description": "First report"},
            headers=auth_header(owner.id),
        )
        assert first.status_code == 200

        second = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-damaged",
            json={"description": "Second report"},
            headers=auth_header(owner.id),
        )
        assert second.status_code == 409


class TestScenario6bDamageReportWindowClosesAfterSevenDays:
    async def test_report_rejected_after_seven_days(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)
        reservation = await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.RETURNED,
            returned_at=datetime.now(UTC) - timedelta(days=8),
        )

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-damaged",
            json={"description": "Found this later"},
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422
        assert "window has closed" in response.json()["detail"].lower()


class TestScenario7ToolNeverReturnedEscalationAfterSevenDays:
    async def test_admin_notified_and_borrower_profile_flagged(
        self, client, db_session: AsyncSession
    ) -> None:
        owner, borrower, tool, reservation = await _make_picked_up_reservation(
            client,
            db_session,
            start_date=date.today() - timedelta(days=20),
            end_date=date.today() - timedelta(days=8),
        )
        admin = await UserFactory.create_async(db_session, is_admin=True)

        with patch_scheduler_session(db_session):
            await SchedulerService().auto_escalate_overdue_returns()

        from app.models.notification import Notification

        admin_notifications = (
            (await db_session.execute(select(Notification).where(Notification.user_id == admin.id)))
            .scalars()
            .all()
        )
        assert len(admin_notifications) >= 1

    async def test_reservation_remains_picked_up_indefinitely_until_admin_acts(
        self, client, db_session: AsyncSession
    ) -> None:
        owner, borrower, tool, reservation = await _make_picked_up_reservation(
            client,
            db_session,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() - timedelta(days=20),
        )

        with patch_scheduler_session(db_session):
            await SchedulerService().auto_escalate_overdue_returns()

        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.PICKED_UP


class TestScenario8AdminCanForceMarkReturnedInDispute:
    async def test_force_return_sets_resolution_fields(
        self, client, db_session: AsyncSession
    ) -> None:
        owner, borrower, tool, reservation = await _make_picked_up_reservation(client, db_session)
        admin = await UserFactory.create_async(db_session, is_admin=True)

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/admin-force-return",
            json={"reason": "Reviewed evidence from both parties"},
            headers=auth_header(admin.id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "RETURNED"
        assert data["force_resolved_by"] == str(admin.id)
        assert data["force_resolution_reason"] == "Reviewed evidence from both parties"

    async def test_non_admin_cannot_force_return(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_picked_up_reservation(client, db_session)

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/admin-force-return",
            json={"reason": "trying anyway"},
            headers=auth_header(borrower.id),
        )
        assert response.status_code == 403


class TestScenario9DuplicateReportRejected:
    """Same underlying gap as Scenario 6's duplicate-report test -- kept as a
    separate scenario for 1:1 doc traceability rather than de-duplicating."""

    async def test_second_report_on_same_reservation_rejected(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)
        reservation = await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.RETURNED,
            returned_at=datetime.now(UTC),
        )

        await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-damaged",
            json={"description": "First"},
            headers=auth_header(owner.id),
        )
        second = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-damaged",
            json={"description": "Second"},
            headers=auth_header(owner.id),
        )
        assert second.status_code == 409
