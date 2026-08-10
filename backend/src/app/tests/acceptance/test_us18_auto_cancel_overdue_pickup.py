"""User Story 18 — Auto-Cancel Overdue Pickup.

The scheduler (`app/services/scheduler.py`) runs this as an hourly APScheduler
job in production; tests run it disabled (`DISABLE_SCHEDULER=true`) so these
tests invoke `SchedulerService().auto_cancel_overdue_pickups()` directly,
patched (see `helpers.patch_scheduler_session`) to share the test's DB
session/transaction instead of opening its own connection.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import utc_to_hst
from app.models.enums import ReservationState
from app.services.scheduler import SchedulerService
from app.tests.acceptance.helpers import (
    auth_header,
    create_tool,
    patch_scheduler_session,
)
from app.tests.factories import ReservationFactory, UserFactory

pytestmark = pytest.mark.acceptance


async def _make_approved_reservation(client, db_session, *, start_days_ago: int):
    owner = await UserFactory.create_async(db_session)
    borrower = await UserFactory.create_async(db_session)
    tool = await create_tool(client, owner)
    today_hst = utc_to_hst(datetime.now(UTC)).date()
    reservation = await ReservationFactory.create_async(
        db_session,
        tool_id=tool["id"],
        borrower_id=borrower.id,
        state=ReservationState.APPROVED,
        start_date=today_hst - timedelta(days=start_days_ago),
        end_date=today_hst + timedelta(days=5),
    )
    return owner, borrower, tool, reservation


class TestScenario1AutoCancelledAfterGracePeriod:
    async def test_reservation_cancelled_both_parties_notified_dates_freed(
        self, client, db_session: AsyncSession
    ) -> None:
        from sqlalchemy import select

        from app.models.notification import Notification

        owner, borrower, tool, reservation = await _make_approved_reservation(
            client, db_session, start_days_ago=4
        )

        with patch_scheduler_session(db_session):
            await SchedulerService().auto_cancel_overdue_pickups()

        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.CANCELLED

        borrower_notifications = (
            (
                await db_session.execute(
                    select(Notification).where(Notification.user_id == borrower.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(borrower_notifications) >= 1

        # Dates are freed: a new request overlapping the cancelled reservation's
        # still-future end date now succeeds (start_date itself is in the past
        # by construction and can't be resubmitted -- new requests must start
        # today or later -- so this exercises the tail end of the freed range).
        new_borrower = await UserFactory.create_async(db_session)
        new_start = reservation.end_date - timedelta(days=1)
        new_request = await client.post(
            "/api/v1/reservations",
            json={
                "tool_id": tool["id"],
                "start_date": str(new_start),
                "end_date": str(reservation.end_date),
            },
            headers=auth_header(new_borrower.id),
        )
        assert new_request.status_code == 201

    async def test_owner_is_also_notified(self, client, db_session: AsyncSession) -> None:
        from sqlalchemy import select

        from app.models.notification import Notification

        owner, borrower, tool, reservation = await _make_approved_reservation(
            client, db_session, start_days_ago=4
        )

        with patch_scheduler_session(db_session):
            await SchedulerService().auto_cancel_overdue_pickups()

        owner_notifications = (
            (await db_session.execute(select(Notification).where(Notification.user_id == owner.id)))
            .scalars()
            .all()
        )
        assert len(owner_notifications) >= 1


class TestScenario2NotAutoCancelledWithinGracePeriod:
    async def test_reservation_remains_approved(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_approved_reservation(
            client, db_session, start_days_ago=2
        )

        with patch_scheduler_session(db_session):
            await SchedulerService().auto_cancel_overdue_pickups()

        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.APPROVED


class TestScenario3PickupWithinGracePeriodPreventsAutoCancellation:
    async def test_picked_up_reservation_is_not_touched_by_job(
        self, client, db_session: AsyncSession
    ) -> None:
        owner, borrower, tool, reservation = await _make_approved_reservation(
            client, db_session, start_days_ago=2
        )

        pickup_response = await client.post(
            f"/api/v1/reservations/{reservation.id}/mark-picked-up",
            headers=auth_header(borrower.id),
        )
        assert pickup_response.status_code == 200

        with patch_scheduler_session(db_session):
            await SchedulerService().auto_cancel_overdue_pickups()

        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.PICKED_UP


class TestScenario4AutoCancelledReservationFreesDateRange:
    async def test_new_request_for_same_dates_accepted(
        self, client, db_session: AsyncSession
    ) -> None:
        owner, borrower, tool, reservation = await _make_approved_reservation(
            client, db_session, start_days_ago=5
        )

        with patch_scheduler_session(db_session):
            await SchedulerService().auto_cancel_overdue_pickups()

        new_borrower = await UserFactory.create_async(db_session)
        new_start = reservation.end_date - timedelta(days=1)
        response = await client.post(
            "/api/v1/reservations",
            json={
                "tool_id": tool["id"],
                "start_date": str(new_start),
                "end_date": str(reservation.end_date),
            },
            headers=auth_header(new_borrower.id),
        )
        assert response.status_code == 201
        assert response.json()["state"] == "REQUESTED"


class TestScenario5GracePeriodTimerEvaluatedInHST:
    async def test_grace_period_uses_hst_not_server_local_time(
        self, client, db_session: AsyncSession
    ) -> None:
        """05:00 UTC is 19:00 the *previous* day in HST (UTC-10) -- so at this
        instant, UTC's and HST's calendar "today" are one day apart. A
        reservation whose start_date is exactly `scheduler_grace_period_days`
        before HST's today sits right at the job's documented strict-less-
        than boundary (see Scenario 1's note): it must NOT be cancelled yet.
        If the job used the server's UTC date instead of converting through
        `app.core.timezone.utc_to_hst`, this same reservation would look one
        day older than it is and get cancelled a day early.
        """
        from unittest.mock import patch

        from app.config import get_settings

        fixed_now_utc = datetime(2026, 3, 15, 5, 0, 0, tzinfo=UTC)
        hst_today = utc_to_hst(fixed_now_utc).date()
        assert hst_today == date(2026, 3, 14)
        grace_days = get_settings().scheduler_grace_period_days

        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)
        reservation = await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.APPROVED,
            start_date=hst_today - timedelta(days=grace_days),
            end_date=hst_today + timedelta(days=5),
        )

        class _FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now_utc.astimezone(tz) if tz else fixed_now_utc

        with (
            patch_scheduler_session(db_session),
            patch("app.services.scheduler.datetime", _FrozenDateTime),
        ):
            await SchedulerService().auto_cancel_overdue_pickups()

        await db_session.refresh(reservation)
        assert reservation.state == ReservationState.APPROVED
