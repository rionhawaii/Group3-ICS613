"""User Story 17 — Confirm Tool Pickup."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReservationState
from app.tests.acceptance.helpers import auth_header, create_tool
from app.tests.factories import ReservationFactory, UserFactory

pytestmark = pytest.mark.acceptance


async def _make_reservation(client, db_session, state=ReservationState.APPROVED, **kwargs):
    owner = await UserFactory.create_async(db_session)
    borrower = await UserFactory.create_async(db_session)
    tool = await create_tool(client, owner)
    kwargs.setdefault("start_date", date.today())
    kwargs.setdefault("end_date", date.today() + timedelta(days=3))
    reservation = await ReservationFactory.create_async(
        db_session, tool_id=tool["id"], borrower_id=borrower.id, state=state, **kwargs
    )
    return owner, borrower, tool, reservation


class TestScenario1BorrowerMarksPickedUpOnOrAfterStartDate:
    async def test_state_becomes_picked_up_with_timestamp(
        self, client, db_session: AsyncSession
    ) -> None:
        owner, borrower, tool, reservation = await _make_reservation(
            client, db_session, start_date=date.today()
        )

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-picked-up",
            headers=auth_header(borrower.id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "PICKED_UP"
        assert data["picked_up_at"] is not None

        # Visible to the owner too.
        owner_view = await client.get(
            f"/api/v1/reservations/{reservation.id}", headers=auth_header(owner.id)
        )
        assert owner_view.json()["picked_up_at"] == data["picked_up_at"]


class TestScenario2CannotMarkPickedUpBeforeStartDate:
    async def test_rejected_status_remains_approved(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_reservation(
            client,
            db_session,
            start_date=date.today() + timedelta(days=5),
            end_date=date.today() + timedelta(days=8),
        )

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-picked-up",
            headers=auth_header(borrower.id),
        )

        assert response.status_code == 422
        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.APPROVED


class TestScenario4BackendRejectsInvalidStatusTransition:
    async def test_rejected_from_requested(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_reservation(
            client, db_session, state=ReservationState.REQUESTED
        )
        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-picked-up",
            headers=auth_header(borrower.id),
        )
        assert response.status_code == 409

    async def test_rejected_from_cancelled(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_reservation(
            client, db_session, state=ReservationState.CANCELLED
        )
        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-picked-up",
            headers=auth_header(borrower.id),
        )
        assert response.status_code == 409

    async def test_rejected_from_denied(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_reservation(
            client, db_session, state=ReservationState.DENIED
        )
        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-picked-up",
            headers=auth_header(borrower.id),
        )
        assert response.status_code == 409

    async def test_rejected_from_returned(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_reservation(
            client, db_session, state=ReservationState.RETURNED
        )
        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-picked-up",
            headers=auth_header(borrower.id),
        )
        assert response.status_code == 409


class TestScenario5NonBorrowerCannotMarkPickedUp:
    async def test_owner_gets_403(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_reservation(client, db_session)

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-picked-up",
            headers=auth_header(owner.id),
        )

        assert response.status_code == 403
        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.APPROVED


class TestScenario6UnauthenticatedCannotMarkPickedUp:
    async def test_returns_401(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_reservation(client, db_session)

        response = await client.post(f"/api/v1/reservations/{reservation.id}/mark-picked-up")

        assert response.status_code == 401
        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.APPROVED


class TestScenario7CannotDoubleConfirmPickup:
    async def test_second_confirm_rejected_timestamp_preserved(
        self, client, db_session: AsyncSession
    ) -> None:
        owner, borrower, tool, reservation = await _make_reservation(client, db_session)

        first = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-picked-up",
            headers=auth_header(borrower.id),
        )
        assert first.status_code == 200
        original_timestamp = first.json()["picked_up_at"]

        second = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-picked-up",
            headers=auth_header(borrower.id),
        )
        assert second.status_code == 409

        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.PICKED_UP
        assert datetime.fromisoformat(original_timestamp) == reservation.picked_up_at
