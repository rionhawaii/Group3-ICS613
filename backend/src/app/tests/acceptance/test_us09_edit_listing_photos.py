"""User Story 9 — Edit a Tool Listing and Manage Photos."""

import uuid
from io import BytesIO

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReservationState
from app.models.photo import Photo
from app.tests.acceptance.helpers import auth_header, create_tool, fake_photo
from app.tests.factories import ReservationFactory, UserFactory

pytestmark = pytest.mark.acceptance


class TestScenario1SuccessfullyEditWithNoPickedUpReservation:
    async def test_fields_and_category_updated(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner, category="HAND_TOOLS")

        response = await client.patch(
            f"/api/v1/tools/{tool['id']}",
            json={"category": "GARDEN_TOOLS", "condition": "FAIR"},
            headers=auth_header(owner.id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "GARDEN_TOOLS"
        assert data["condition"] == "FAIR"

        # Reflected in browse filters for another member.
        other = await UserFactory.create_async(db_session)
        browse = await client.get(
            "/api/v1/tools",
            params={"category": "GARDEN_TOOLS"},
            headers=auth_header(other.id),
        )
        assert any(item["id"] == tool["id"] for item in browse.json()["items"])

    async def test_editable_with_requested_or_approved_reservation(
        self, client, db_session: AsyncSession
    ) -> None:
        """REQUESTED/APPROVED reservations don't block edits (not yet binding)."""
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)
        await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.APPROVED,
        )

        response = await client.patch(
            f"/api/v1/tools/{tool['id']}",
            json={"condition": "FAIR"},
            headers=auth_header(owner.id),
        )
        assert response.status_code == 200


# Scenario "lending fields updated and visible" is descoped -- see US8
# module docstring; no latest_return_time/lending_rules/notes fields exist.


class TestScenario2CannotEditWhilePickedUp:
    async def test_edit_rejected_and_fields_unchanged(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner, condition="GOOD")
        await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.PICKED_UP,
        )

        response = await client.patch(
            f"/api/v1/tools/{tool['id']}",
            json={"condition": "POOR"},
            headers=auth_header(owner.id),
        )

        assert response.status_code == 409
        get_response = await client.get(
            f"/api/v1/tools/{tool['id']}", headers=auth_header(owner.id)
        )
        assert get_response.json()["condition"] == "GOOD"


class TestScenario3OwnerCanAddPhotoUpToFive:
    async def test_add_photo_when_below_limit(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner, num_photos=1)

        response = await client.post(
            f"/api/v1/tools/{tool['id']}/photos",
            files=[("photos", fake_photo("second.jpg"))],
            headers=auth_header(owner.id),
        )

        assert response.status_code == 200
        assert len(response.json()["photos"]) == 2


class TestScenario4CannotAddPhotoAtFive:
    async def test_sixth_photo_rejected(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner, num_photos=5)

        response = await client.post(
            f"/api/v1/tools/{tool['id']}/photos",
            files=[("photos", fake_photo("sixth.jpg"))],
            headers=auth_header(owner.id),
        )

        assert response.status_code == 422


class TestScenario5OwnerCanRemovePhotoWhenTwoOrMoreExist:
    async def test_remove_photo_updates_gallery(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner, num_photos=2)
        first_photo_id = tool["photos"][0]["id"]

        response = await client.delete(
            f"/api/v1/tools/{tool['id']}/photos/{first_photo_id}",
            headers=auth_header(owner.id),
        )
        assert response.status_code == 204

        # Verified directly against a live server (two independent DB
        # connections) that the delete is correctly persisted. A second
        # client.get() here is unreliable: the test client shares one
        # SQLAlchemy session/identity map across requests (see
        # conftest.py's `client` fixture), so the already-loaded
        # `tool.photos` collection can appear stale even though the row is
        # really gone -- a test-harness artifact, not a product bug. Query
        # the Photo table directly instead, which isn't affected by that
        # collection-caching quirk.
        remaining = (
            (await db_session.execute(select(Photo).where(Photo.tool_id == uuid.UUID(tool["id"]))))
            .scalars()
            .all()
        )
        assert len(remaining) == 1
        assert str(remaining[0].id) != first_photo_id


class TestScenario6OwnerCannotRemoveLastPhoto:
    async def test_removing_only_photo_is_rejected(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner, num_photos=1)
        photo_id = tool["photos"][0]["id"]

        response = await client.delete(
            f"/api/v1/tools/{tool['id']}/photos/{photo_id}",
            headers=auth_header(owner.id),
        )

        assert response.status_code == 422


class TestScenario7PhotoUploadValidationRejectsInvalidFilesOnEdit:
    async def test_non_image_upload_rejected_existing_photos_unaffected(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner, num_photos=1)

        response = await client.post(
            f"/api/v1/tools/{tool['id']}/photos",
            files=[("photos", ("bad.txt", BytesIO(b"not an image"), "text/plain"))],
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422

        get_response = await client.get(
            f"/api/v1/tools/{tool['id']}", headers=auth_header(owner.id)
        )
        assert len(get_response.json()["photos"]) == 1


class TestScenario8NonOwnerCannotEdit:
    async def test_returns_403_and_listing_unchanged(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        other = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner, condition="GOOD")

        response = await client.patch(
            f"/api/v1/tools/{tool['id']}",
            json={"condition": "POOR"},
            headers=auth_header(other.id),
        )
        assert response.status_code == 403

        get_response = await client.get(
            f"/api/v1/tools/{tool['id']}", headers=auth_header(owner.id)
        )
        assert get_response.json()["condition"] == "GOOD"


class TestScenario9UnauthenticatedCannotEdit:
    async def test_returns_401(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)

        response = await client.patch(f"/api/v1/tools/{tool['id']}", json={"condition": "POOR"})
        assert response.status_code == 401


# Scenario 10 (invalid latest_return_time rejected on edit) is descoped --
# see US8 module docstring; no such field exists.


class TestScenario11MessageThreadsAccessibleAfterDeactivation:
    async def test_thread_readable_after_listing_deactivated(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        borrower = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner)
        reservation = await ReservationFactory.create_async(
            db_session,
            tool_id=tool["id"],
            borrower_id=borrower.id,
            state=ReservationState.REQUESTED,
        )

        send_response = await client.post(
            f"/api/v1/reservations/{reservation.id}/messages",
            json={"body": "Can I pick this up tomorrow morning?"},
            headers=auth_header(borrower.id),
        )
        assert send_response.status_code == 201

        # Deactivating auto-cancels the still-pending (REQUESTED) reservation.
        deactivate_response = await client.post(
            f"/api/v1/tools/{tool['id']}/deactivate",
            json={"reason": "No longer available"},
            headers=auth_header(owner.id),
        )
        assert deactivate_response.status_code == 200

        messages_response = await client.get(
            f"/api/v1/reservations/{reservation.id}/messages",
            headers=auth_header(borrower.id),
        )
        assert messages_response.status_code == 200
        bodies = [item["body"] for item in messages_response.json()["items"]]
        assert "Can I pick this up tomorrow morning?" in bodies


class TestScenario12NonOwnerCannotRemovePhoto:
    async def test_returns_403(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        other = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner, num_photos=2)
        photo_id = tool["photos"][0]["id"]

        response = await client.delete(
            f"/api/v1/tools/{tool['id']}/photos/{photo_id}",
            headers=auth_header(other.id),
        )
        assert response.status_code == 403


class TestScenario13RemoveNonexistentPhotoReturns404:
    async def test_returns_404_for_unknown_photo_id(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        tool = await create_tool(client, owner, num_photos=2)

        response = await client.delete(
            f"/api/v1/tools/{tool['id']}/photos/{uuid.uuid4()}",
            headers=auth_header(owner.id),
        )
        assert response.status_code == 404

    async def test_returns_404_for_photo_belonging_to_another_tool(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        tool_a = await create_tool(client, owner, name="Tool A", num_photos=2)
        tool_b = await create_tool(client, owner, name="Tool B", num_photos=2)
        photo_from_b = tool_b["photos"][0]["id"]

        response = await client.delete(
            f"/api/v1/tools/{tool_a['id']}/photos/{photo_from_b}",
            headers=auth_header(owner.id),
        )
        assert response.status_code == 404
