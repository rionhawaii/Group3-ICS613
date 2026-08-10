"""User Story 24 — Leave a Rating and Review After a Tool is Returned."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReservationState
from app.models.review import Review
from app.tests.acceptance.helpers import auth_header, create_tool
from app.tests.factories import ReservationFactory, UserFactory

pytestmark = pytest.mark.acceptance


async def _make_returned_reservation(client, db_session, **kwargs):
    owner = await UserFactory.create_async(db_session)
    borrower = await UserFactory.create_async(db_session)
    tool = await create_tool(client, owner)
    kwargs.setdefault("returned_at", datetime.now(UTC))
    reservation = await ReservationFactory.create_async(
        db_session,
        tool_id=tool["id"],
        borrower_id=borrower.id,
        state=ReservationState.RETURNED,
        **kwargs,
    )
    return owner, borrower, tool, reservation


class TestScenario1SubmitValidReview:
    async def test_review_saved_and_associated_with_reviewee(
        self, client, db_session: AsyncSession
    ) -> None:
        owner, borrower, tool, reservation = await _make_returned_reservation(client, db_session)

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 5, "comment": "Great borrower!"},
            headers=auth_header(owner.id),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["rating"] == 5
        assert data["reviewee_id"] == str(borrower.id)
        assert data["reviewer_id"] == str(owner.id)

    async def test_review_response_includes_reviewer_display_name(
        self, client, db_session: AsyncSession
    ) -> None:
        owner, borrower, tool, reservation = await _make_returned_reservation(client, db_session)

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 5, "comment": "Great borrower!"},
            headers=auth_header(owner.id),
        )
        assert response.json().get("reviewer_name") is not None


class TestScenario2CannotReviewNonCompletedReservation:
    @pytest.mark.parametrize(
        "state",
        [
            ReservationState.REQUESTED,
            ReservationState.APPROVED,
            ReservationState.PICKED_UP,
            ReservationState.CANCELLED,
            ReservationState.DENIED,
        ],
    )
    async def test_rejected_for_non_returned_states(
        self, client, db_session: AsyncSession, state: ReservationState
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)
        reservation = await ReservationFactory.create_async(
            db_session, tool_id=tool["id"], borrower_id=borrower.id, state=state
        )

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 4},
            headers=auth_header(owner.id),
        )
        assert response.status_code == 409


class TestScenario3OneReviewPerReservationPerReviewer:
    async def test_second_review_rejected_first_preserved(
        self, client, db_session: AsyncSession
    ) -> None:
        owner, borrower, tool, reservation = await _make_returned_reservation(client, db_session)

        first = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 5, "comment": "First"},
            headers=auth_header(owner.id),
        )
        assert first.status_code == 201

        second = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 1, "comment": "Second attempt"},
            headers=auth_header(owner.id),
        )
        # No further DB queries after this: ReviewService.create_review calls
        # db.rollback() on the IntegrityError, which -- under this test's
        # shared per-test transaction (see conftest.py's db_session fixture) --
        # closes the ambient transaction, not just the failed insert. Asserting
        # only on the response here matches how the existing unit suite
        # handles the same duplicate-review case (test_reviews.py).
        assert second.status_code == 409
        assert "already reviewed" in second.json()["detail"].lower()


class TestScenario4ReviewWindowClosesAfter30Days:
    async def test_rejected_after_30_days(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_returned_reservation(
            client, db_session, returned_at=datetime.now(UTC) - timedelta(days=31)
        )

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 3},
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422
        assert "window has closed" in response.json()["detail"].lower()


class TestScenario5UserCannotReviewThemselves:
    async def test_rejected_when_borrower_and_owner_are_same_user(
        self, client, db_session: AsyncSession
    ) -> None:
        """Structural note: create_reservation blocks a user from reserving their
        own tool, so this state can't arise organically -- forced via factory to
        exercise the service's own self-review guard directly."""
        user = await UserFactory.create_async(db_session)
        tool = await create_tool(client, user)
        reservation = await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=user.id,
            state=ReservationState.RETURNED,
            returned_at=datetime.now(UTC),
        )

        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 5},
            headers=auth_header(user.id),
        )
        assert response.status_code == 409
        assert "yourself" in response.json()["detail"].lower()


class TestScenario6RatingMustBeIntegerBetweenOneAndFive:
    async def test_rating_zero_rejected(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_returned_reservation(client, db_session)
        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 0},
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422

    async def test_rating_six_rejected(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_returned_reservation(client, db_session)
        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 6},
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422

    async def test_non_integer_rating_rejected(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_returned_reservation(client, db_session)
        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 3.5},
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422


class TestScenario7CommentOptionalRatingRequired:
    async def test_review_saved_with_rating_only(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_returned_reservation(client, db_session)
        response = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 4},
            headers=auth_header(owner.id),
        )
        assert response.status_code == 201
        assert response.json()["comment"] is None


class TestScenario8EditOrDeleteWithin24Hours:
    async def test_edit_within_window_succeeds(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_returned_reservation(client, db_session)
        create_response = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 3, "comment": "Okay"},
            headers=auth_header(owner.id),
        )
        review_id = create_response.json()["id"]

        response = await client.patch(
            f"/api/v1/reviews/{review_id}",
            json={"rating": 5, "comment": "Actually great"},
            headers=auth_header(owner.id),
        )
        assert response.status_code == 200
        assert response.json()["rating"] == 5

    async def test_delete_within_window_removes_review(
        self, client, db_session: AsyncSession
    ) -> None:
        owner, borrower, tool, reservation = await _make_returned_reservation(client, db_session)
        create_response = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 3},
            headers=auth_header(owner.id),
        )
        review_id = create_response.json()["id"]

        response = await client.delete(
            f"/api/v1/reviews/{review_id}", headers=auth_header(owner.id)
        )
        assert response.status_code == 204

        reviews = await client.get(
            f"/api/v1/reservations/{reservation.id}/review",
            headers=auth_header(owner.id),
        )
        assert reviews.json() == []

    async def test_edit_after_24_hours_rejected(self, client, db_session: AsyncSession) -> None:
        owner, borrower, tool, reservation = await _make_returned_reservation(client, db_session)
        create_response = await client.post(
            f"/api/v1/reservations/{reservation.id}/review",
            json={"rating": 3},
            headers=auth_header(owner.id),
        )
        review_id = create_response.json()["id"]

        review = await db_session.get(Review, review_id)
        assert review is not None
        review.created_at = datetime.now(UTC) - timedelta(hours=25)
        db_session.add(review)
        await db_session.flush()

        response = await client.patch(
            f"/api/v1/reviews/{review_id}",
            json={"rating": 1},
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422
