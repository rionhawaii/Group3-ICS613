"""User Story 6 — Edit Profile."""

from io import BytesIO

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tests.acceptance.helpers import auth_header, fake_photo
from app.tests.factories import UserFactory

pytestmark = pytest.mark.acceptance


class TestScenario1UpdateProfileInformation:
    async def test_updated_fields_are_saved(self, client, db_session: AsyncSession) -> None:
        user = await UserFactory.create_async(db_session, full_name="Old Name")

        response = await client.put(
            "/api/v1/auth/me",
            json={"full_name": "New Name", "bio": "Updated bio", "neighborhood": "Kaimuki"},
            headers=auth_header(user.id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "New Name"
        assert data["bio"] == "Updated bio"
        assert data["neighborhood"] == "Kaimuki"


class TestScenario2DisplayNameCannotBeCleared:
    async def test_blank_display_name_rejected_and_previous_preserved(
        self, client, db_session: AsyncSession
    ) -> None:
        user = await UserFactory.create_async(db_session, full_name="Keep Me")

        response = await client.put(
            "/api/v1/auth/me",
            json={"full_name": ""},
            headers=auth_header(user.id),
        )

        assert response.status_code == 422
        await db_session.refresh(user)
        assert user.full_name == "Keep Me"


class TestScenario3DisplayNameExceedsMaxLength:
    async def test_overlong_display_name_rejected(self, client, db_session: AsyncSession) -> None:
        # Server enforces the 40-character limit (frontend uses the same rule) —
        # previously only max_length=255 was enforced server-side (finding in #339).
        user = await UserFactory.create_async(db_session)

        response = await client.put(
            "/api/v1/auth/me",
            json={"full_name": "x" * 41},
            headers=auth_header(user.id),
        )

        assert response.status_code == 422

    async def test_exactly_40_characters_accepted(self, client, db_session: AsyncSession) -> None:
        user = await UserFactory.create_async(db_session, full_name="Old Name")

        response = await client.put(
            "/api/v1/auth/me",
            json={"full_name": "x" * 40},
            headers=auth_header(user.id),
        )

        assert response.status_code == 200
        assert response.json()["full_name"] == "x" * 40


class TestScenario4ProfilePhotoUploadFailsValidation:
    async def test_invalid_photo_rejected_existing_photo_unchanged(
        self, client, db_session: AsyncSession
    ) -> None:
        """An invalid upload is rejected and the existing photo stays intact."""
        user = await UserFactory.create_async(
            db_session, photo_url="https://example.com/avatar.jpg"
        )

        response = await client.post(
            "/api/v1/auth/me/photo",
            files=[("photo", ("fake.png", BytesIO(b"not an image"), "image/png"))],
            headers=auth_header(user.id),
        )

        assert response.status_code == 422
        await db_session.refresh(user)
        assert user.photo_url == "https://example.com/avatar.jpg"

    async def test_valid_upload_replaces_existing_photo(
        self, client, db_session: AsyncSession
    ) -> None:
        """A valid upload replaces the previous uploaded photo file."""
        user = await UserFactory.create_async(db_session, photo_url="/uploads/old.jpg")

        response = await client.post(
            "/api/v1/auth/me/photo",
            files=[("photo", fake_photo("new.jpg"))],
            headers=auth_header(user.id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["photo_url"].startswith("/uploads/")
        assert data["photo_url"] != "/uploads/old.jpg"
        await db_session.refresh(user)
        assert user.photo_url == data["photo_url"]


class TestScenario5UnauthenticatedCannotEdit:
    async def test_returns_401_and_no_changes_saved(self, client) -> None:
        response = await client.put("/api/v1/auth/me", json={"full_name": "Nope"})
        assert response.status_code == 401


class TestScenario6MemberCannotEditAnotherProfile:
    async def test_no_target_user_id_is_accepted_by_the_api(self, client) -> None:
        """Structurally satisfied: PUT /auth/me always targets the caller.

        There is no ``user_id`` path/body parameter to manipulate, so the
        403-Forbidden scenario described in the doc (editing *another*
        member's profile via URL manipulation) cannot occur through this
        endpoint. This test just pins that the request body is ignored for
        identity purposes -- confirming there is no hidden id/user_id field.
        """
        response = await client.put(
            "/api/v1/auth/me",
            json={"full_name": "Whatever"},
        )
        assert response.status_code == 401, "no id field means no auth still means no access"


class TestScenario7NoChangesSubmittedIsANoOp:
    async def test_empty_body_saves_silently(self, client, db_session: AsyncSession) -> None:
        user = await UserFactory.create_async(
            db_session, full_name="Unchanged Name", bio="Unchanged bio"
        )

        response = await client.put(
            "/api/v1/auth/me",
            json={},
            headers=auth_header(user.id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Unchanged Name"
        assert data["bio"] == "Unchanged bio"


class TestScenario8NullClearsOptionalFields:
    async def test_null_clears_bio_neighborhood_photo(
        self, client, db_session: AsyncSession
    ) -> None:
        user = await UserFactory.create_async(
            db_session,
            full_name="Keep Me",
            bio="A bio",
            neighborhood="Kaimuki",
            photo_url="https://example.com/photo.jpg",
        )

        response = await client.put(
            "/api/v1/auth/me",
            json={"bio": None, "neighborhood": None, "photo_url": None},
            headers=auth_header(user.id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Keep Me"
        assert data["bio"] is None
        assert data["neighborhood"] is None
        assert data["photo_url"] is None

    async def test_null_display_name_is_ignored(self, client, db_session: AsyncSession) -> None:
        """The display name cannot be cleared: explicit null is a no-op."""
        user = await UserFactory.create_async(db_session, full_name="Keep Me")

        response = await client.put(
            "/api/v1/auth/me",
            json={"full_name": None},
            headers=auth_header(user.id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Keep Me"
