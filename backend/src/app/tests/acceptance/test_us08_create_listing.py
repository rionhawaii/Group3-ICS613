"""User Story 8 — Create a Tool Listing.

Structural note up front: the doc's category examples ("Power Tools",
"Garden", "Kitchen", "Ladders", "Other") and its admin-managed category list
(User Story 28) don't match reality. ``ToolCategory`` (app/models/enums.py)
is a fixed Python enum -- ``HAND_TOOLS``, ``POWER_TOOLS``, ``GARDEN_TOOLS``,
``CLEANING_TOOLS``, ``OUTDOOR_GEAR`` -- with no DB-backed, admin-editable
list, no "Kitchen"/"Ladders" categories, and no add/remove capability. That
whole gap is tracked once under User Story 28's acceptance module rather
than repeated here.

Also missing from the ``Tool`` model entirely: ``latest_return_time``,
lending rules, and notes-for-borrowers. These were flagged as mock-only
frontend fields with no backend equivalent early on and never built; the
team decided against adding them (see QA_NOTES.local.md, 2026-08-09
triage). Scenarios that hinged on those fields have been removed rather
than left skipped.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import Tool
from app.tests.acceptance.helpers import auth_header, create_tool, fake_photo
from app.tests.factories import UserFactory

pytestmark = pytest.mark.acceptance


class TestScenario1SuccessfullyCreateNewListing:
    async def test_listing_created_active_with_photos(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)

        tool = await create_tool(
            client,
            owner,
            name="Circular Saw",
            category="POWER_TOOLS",
            condition="GOOD",
            description="A reliable circular saw.",
            num_photos=2,
        )

        assert tool["is_active"] is True
        assert tool["owner_id"] == str(owner.id)
        assert len(tool["photos"]) == 2
        # Photos are stored in upload order; first is the thumbnail.
        assert tool["photos"][0]["display_order"] == 1

        # Appears in browse results filtered by category, to a different member.
        other = await UserFactory.create_async(db_session)
        browse = await client.get(
            "/api/v1/tools",
            params={"category": "POWER_TOOLS"},
            headers=auth_header(other.id),
        )
        assert browse.status_code == 200
        assert any(item["id"] == tool["id"] for item in browse.json()["items"])


class TestScenario2RequiredFieldsMissing:
    async def test_missing_name_is_rejected(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        response = await client.post(
            "/api/v1/tools",
            data={"category": "POWER_TOOLS", "condition": "GOOD"},
            files=[("photos", fake_photo())],
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422

    async def test_missing_category_is_rejected(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        response = await client.post(
            "/api/v1/tools",
            data={"name": "Drill", "condition": "GOOD"},
            files=[("photos", fake_photo())],
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422

    async def test_missing_condition_is_rejected(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        response = await client.post(
            "/api/v1/tools",
            data={"name": "Drill", "category": "POWER_TOOLS"},
            files=[("photos", fake_photo())],
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422

    async def test_missing_description_is_rejected(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        response = await client.post(
            "/api/v1/tools",
            data={"name": "Drill", "category": "POWER_TOOLS", "condition": "GOOD"},
            files=[("photos", fake_photo())],
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422


class TestScenario3PhotoUploadValidationRejectsInvalidFiles:
    async def test_non_image_file_is_rejected(self, client, db_session: AsyncSession) -> None:
        from io import BytesIO

        owner = await UserFactory.create_async(db_session)
        response = await client.post(
            "/api/v1/tools",
            data={"name": "Drill", "category": "POWER_TOOLS", "condition": "GOOD"},
            files=[("photos", ("not-a-photo.txt", BytesIO(b"hello world"), "text/plain"))],
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422

    async def test_more_than_five_photos_is_rejected(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        response = await client.post(
            "/api/v1/tools",
            data={"name": "Drill", "category": "POWER_TOOLS", "condition": "GOOD"},
            files=[("photos", fake_photo(f"p{i}.jpg")) for i in range(6)],
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422


class TestScenario4ZeroPhotosIsRejected:
    async def test_no_photos_is_rejected(self, client, db_session: AsyncSession) -> None:
        owner = await UserFactory.create_async(db_session)
        response = await client.post(
            "/api/v1/tools",
            data={"name": "Drill", "category": "POWER_TOOLS", "condition": "GOOD"},
            headers=auth_header(owner.id),
        )
        assert response.status_code == 422


# Scenario 5 (latest_return_time format validation) is descoped -- see
# module docstring; no such field exists on Tool.


class TestScenario6UnauthenticatedCannotCreateListing:
    async def test_returns_401(self, client) -> None:
        response = await client.post(
            "/api/v1/tools",
            data={"name": "Drill", "category": "POWER_TOOLS", "condition": "GOOD"},
        )
        assert response.status_code == 401


class TestScenario7ListingNameMustBeUniquePerOwner:
    async def test_duplicate_name_for_same_owner_is_rejected(
        self, client, db_session: AsyncSession
    ) -> None:
        owner = await UserFactory.create_async(db_session)
        await create_tool(client, owner, name="Circular Saw")

        response = await client.post(
            "/api/v1/tools",
            data={
                "name": "Circular Saw",
                "category": "POWER_TOOLS",
                "condition": "GOOD",
                "description": "A duplicate saw.",
            },
            files=[("photos", fake_photo())],
            headers=auth_header(owner.id),
        )
        assert response.status_code == 409

        count = (
            (
                await db_session.execute(
                    select(Tool).where(Tool.owner_id == owner.id, Tool.name == "Circular Saw")
                )
            )
            .scalars()
            .all()
        )
        assert len(count) == 1
