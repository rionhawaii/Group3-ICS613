"""User Story 5 — Set Up Profile.

Note: the API has no dedicated "profile setup" endpoint distinct from "edit
profile" (both are ``PUT /api/v1/auth/me``; see app/api/v1/auth.py). Scenarios
that depend on a setup-vs-edit distinction, or on fields the schema doesn't
have (required display name), are marked as gaps below rather than silently
skipped, since they only manifest on the actual UserUpdate schema
(app/schemas/user.py). Profile-photo upload IS implemented (POST
``/api/v1/auth/me/photo``) — see TestScenario4.
"""

from io import BytesIO

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tests.acceptance.helpers import auth_header, fake_photo
from app.tests.factories import UserFactory

pytestmark = pytest.mark.acceptance


class TestScenario1SetUpProfileAfterFirstLogin:
    async def test_profile_fields_saved_and_visible(self, client, db_session: AsyncSession) -> None:
        user = await UserFactory.create_async(db_session, full_name=None)

        response = await client.put(
            "/api/v1/auth/me",
            json={
                "full_name": "Jordan Kim",
                "bio": "I lend power tools on weekends.",
                "neighborhood": "Manoa",
            },
            headers=auth_header(user.id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Jordan Kim"
        assert data["bio"] == "I lend power tools on weekends."
        assert data["neighborhood"] == "Manoa"


class TestScenario2DisplayNameMissingOrBlank:
    async def test_blank_display_name_is_rejected(self, client, db_session: AsyncSession) -> None:
        user = await UserFactory.create_async(db_session, full_name="Original Name")

        response = await client.put(
            "/api/v1/auth/me",
            json={"full_name": "   "},
            headers=auth_header(user.id),
        )

        assert response.status_code == 422
        await db_session.refresh(user)
        assert user.full_name == "Original Name"


class TestScenario3DisplayNameExceedsMaxLength:
    async def test_overlong_display_name_is_rejected(
        self, client, db_session: AsyncSession
    ) -> None:
        # UserUpdate.full_name (app/schemas/user.py) enforces max_length=255.
        user = await UserFactory.create_async(db_session)

        response = await client.put(
            "/api/v1/auth/me",
            json={"full_name": "x" * 256},
            headers=auth_header(user.id),
        )

        assert response.status_code == 422


class TestScenario4ProfilePhotoUploadFailsValidation:
    async def test_non_image_or_oversized_photo_rejected(
        self, client, db_session: AsyncSession
    ) -> None:
        """Given the user attempts to upload a photo that is not an image or
        exceeds the size limit, the system rejects the photo."""
        user = await UserFactory.create_async(db_session)

        # Non-image bytes declared as image/png -> magic-byte mismatch.
        non_image = await client.post(
            "/api/v1/auth/me/photo",
            files=[("photo", ("fake.png", BytesIO(b"this is not an image"), "image/png"))],
            headers=auth_header(user.id),
        )
        assert non_image.status_code == 422
        await db_session.refresh(user)
        assert user.photo_url is None

        # Oversized file (over the 5 MB default) -> rejected.
        oversized = await client.post(
            "/api/v1/auth/me/photo",
            files=[
                (
                    "photo",
                    (
                        "big.jpg",
                        BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * (5 * 1024 * 1024)),
                        "image/jpeg",
                    ),
                )
            ],
            headers=auth_header(user.id),
        )
        assert oversized.status_code == 422
        await db_session.refresh(user)
        assert user.photo_url is None

    async def test_valid_photo_uploaded_and_visible(self, client, db_session: AsyncSession) -> None:
        """A valid image upload sets photo_url to a /uploads/ path."""
        user = await UserFactory.create_async(db_session)

        response = await client.post(
            "/api/v1/auth/me/photo",
            files=[("photo", fake_photo("profile.jpg"))],
            headers=auth_header(user.id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["photo_url"].startswith("/uploads/")
        assert data["id"] == str(user.id)

        me = await client.get("/api/v1/auth/me", headers=auth_header(user.id))
        assert me.status_code == 200
        assert me.json()["photo_url"] == data["photo_url"]


class TestScenario5UnauthenticatedCannotAccessProfileSetup:
    async def test_returns_401(self, client) -> None:
        response = await client.put("/api/v1/auth/me", json={"full_name": "Someone"})
        assert response.status_code == 401
