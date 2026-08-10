"""User Story 3 — Log In Securely."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tests.acceptance.helpers import auth_header
from app.tests.factories import PendingUserFactory, UserFactory

pytestmark = pytest.mark.acceptance


class TestScenario1LoginWithValidCredentials:
    async def test_active_user_receives_session_token(
        self, client, db_session: AsyncSession
    ) -> None:
        await UserFactory.create_async(db_session, email="us3-scenario1@example.com")

        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "us3-scenario1@example.com",
                "password": "Password123!",  # pragma: allowlist secret
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] and data["refresh_token"]
        # "Redirected to member dashboard" is a frontend routing concern.


class TestScenario2CannotLoginUntilVerified:
    async def test_email_pending_login_rejected(self, client, db_session: AsyncSession) -> None:
        await PendingUserFactory.create_async(db_session, email="us3-scenario2@example.com")

        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "us3-scenario2@example.com",
                "password": "Password123!",  # pragma: allowlist secret
            },
        )

        assert response.status_code == 401
        # Message is deliberately generic (see Scenario 3 / TestLoginDoesNotLeakAccountState
        # in app.tests.test_auth) rather than "email must be verified" — the frontend is
        # expected to offer a resend-verification link on any 401 from /login, not branch
        # on server-supplied detail text. Not independently API-testable beyond the 401.


class TestScenario3LoginWithInvalidCredentials:
    async def test_unknown_email_returns_generic_error(self, client) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nobody-us3@example.com",
                "password": "whatever1!",  # pragma: allowlist secret
            },
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"

    async def test_wrong_password_returns_generic_error(
        self, client, db_session: AsyncSession
    ) -> None:
        await UserFactory.create_async(db_session, email="us3-scenario3@example.com")

        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "us3-scenario3@example.com",
                "password": "WrongPassword1!",  # pragma: allowlist secret
            },
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"


class TestScenario4Logout:
    async def test_logout_returns_success(self, client, db_session: AsyncSession) -> None:
        user = await UserFactory.create_async(db_session, email="us3-scenario4a@example.com")
        response = await client.post("/api/v1/auth/logout", headers=auth_header(user.id))
        assert response.status_code == 200

    async def test_protected_route_rejected_after_logout(
        self, client, db_session: AsyncSession
    ) -> None:
        user = await UserFactory.create_async(db_session, email="us3-scenario4b@example.com")
        headers = auth_header(user.id)

        await client.post("/api/v1/auth/logout", headers=headers)
        response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 401
