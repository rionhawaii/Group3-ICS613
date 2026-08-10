"""User Story 32 — Admin Views Moderation History.

`GET /api/v1/admin/audit-log` (app/api/v1/admin.py) already covers the core
of this story: every suspend/reactivate/delete/tool-deactivate/reactivate/
force-return action is recorded via `AdminService._audit` with actor_id,
action_type, target_type, target_id, reason, and created_at. It supports
filtering by action_type, target_type, target_id, and a date range; the
one filter still missing is by the acting admin (actor_id).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tests.acceptance.helpers import auth_header, make_admin
from app.tests.factories import UserFactory

pytestmark = pytest.mark.acceptance


class TestScenario1AdminViewsModerationHistory:
    async def test_actions_listed_with_type_target_admin_timestamp_reason(
        self, client, db_session: AsyncSession
    ) -> None:
        admin = await make_admin(db_session)
        member = await UserFactory.create_async(db_session)
        await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "policy violation"},
            headers=auth_header(admin.id),
        )

        response = await client.get("/api/v1/admin/audit-log", headers=auth_header(admin.id))

        assert response.status_code == 200
        items = response.json()["items"]
        entry = next(i for i in items if i["target_id"] == str(member.id))
        assert entry["action_type"] == "USER_SUSPEND"
        assert entry["actor_id"] == str(admin.id)
        assert entry["reason"] == "policy violation"
        assert entry["created_at"] is not None

    async def test_filterable_by_action_type(self, client, db_session: AsyncSession) -> None:
        admin = await make_admin(db_session)
        member = await UserFactory.create_async(db_session)
        await client.post(
            f"/api/v1/admin/users/{member.id}/deactivate",
            json={"reason": "x"},
            headers=auth_header(admin.id),
        )

        response = await client.get(
            "/api/v1/admin/audit-log",
            params={"action_type": "USER_SUSPEND"},
            headers=auth_header(admin.id),
        )
        assert response.status_code == 200
        assert all(i["action_type"] == "USER_SUSPEND" for i in response.json()["items"])


class TestScenario2AdminFiltersModerationHistory:
    async def test_filterable_by_member_and_date_range(
        self, client, db_session: AsyncSession
    ) -> None:
        """Filtering by the member (target_id) and by date range both work;
        filtering by the acting admin is still missing (see
        test_filterable_by_acting_admin below)."""
        admin = await make_admin(db_session)
        member_a = await UserFactory.create_async(db_session)
        member_b = await UserFactory.create_async(db_session)
        await client.post(
            f"/api/v1/admin/users/{member_a.id}/deactivate",
            json={"reason": "x"},
            headers=auth_header(admin.id),
        )
        await client.post(
            f"/api/v1/admin/users/{member_b.id}/deactivate",
            json={"reason": "y"},
            headers=auth_header(admin.id),
        )

        response = await client.get(
            "/api/v1/admin/audit-log",
            params={"target_id": str(member_a.id)},
            headers=auth_header(admin.id),
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert all(i["target_id"] == str(member_a.id) for i in items)
        assert not any(i["target_id"] == str(member_b.id) for i in items)

        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        by_date = await client.get(
            "/api/v1/admin/audit-log",
            params={"date_from": future},
            headers=auth_header(admin.id),
        )
        assert by_date.status_code == 200
        assert by_date.json()["items"] == []

    async def test_filterable_by_acting_admin(self, client, db_session: AsyncSession) -> None:
        admin_one = await make_admin(db_session)
        admin_two = await make_admin(db_session)
        member_a = await UserFactory.create_async(db_session)
        member_b = await UserFactory.create_async(db_session)
        await client.post(
            f"/api/v1/admin/users/{member_a.id}/deactivate",
            json={"reason": "x"},
            headers=auth_header(admin_one.id),
        )
        await client.post(
            f"/api/v1/admin/users/{member_b.id}/deactivate",
            json={"reason": "y"},
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


class TestScenario3NoRecordsMatchFilter:
    async def test_empty_result_set_for_unused_action_type(
        self, client, db_session: AsyncSession
    ) -> None:
        admin = await make_admin(db_session)

        response = await client.get(
            "/api/v1/admin/audit-log",
            params={"action_type": "SOME_ACTION_NOBODY_HAS_TAKEN"},
            headers=auth_header(admin.id),
        )
        assert response.status_code == 200
        assert response.json()["items"] == []


class TestScenario4NonAdminCannotViewModerationHistory:
    async def test_returns_403(self, client, db_session: AsyncSession) -> None:
        non_admin = await UserFactory.create_async(db_session)

        response = await client.get("/api/v1/admin/audit-log", headers=auth_header(non_admin.id))
        assert response.status_code == 403
