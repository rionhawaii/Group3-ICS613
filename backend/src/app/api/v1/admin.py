"""Admin endpoints."""

import csv
import io
import uuid
from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user, get_db
from app.core.exceptions import ValidationError
from app.core.timezone import hst_to_utc
from app.models.user import User
from app.schemas.admin import (
    AdminUserDeactivate,
    AdminUserDelete,
    AdminUserReactivate,
    AuditLogResponse,
)
from app.schemas.common import PaginatedResponse
from app.schemas.reservation import ReservationResponse
from app.schemas.user import UserProfile
from app.services.admin import AdminService

router = APIRouter()


def _parse_iso_datetime(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    """Parse an ISO datetime query param.

    A date-only value (``YYYY-MM-DD``) is interpreted as an HST calendar day
    (the UI shows HST timestamps): midnight HST for ``date_from``, or
    23:59:59.999999 HST when ``end_of_day=True`` for ``date_to``, then
    converted to UTC so the entire selected HST day is included in
    ``created_at <= date_to`` filters.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError(
            f"Invalid date format: '{value}'. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
        ) from None
    if len(value) == 10:  # date-only -> HST day, convert to UTC
        if end_of_day:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return cast(datetime, hst_to_utc(parsed))
    return parsed


# ── User listing ────────────────────────────────────────────────────────
@router.get("/users", response_model=PaginatedResponse[UserProfile])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[UserProfile]:
    """Admin-only: list all non-deleted users with optional filters."""
    service = AdminService()
    users, total = await service.list_users(
        db,
        status=status_filter,
        search=search,
        page=page,
        page_size=page_size,
    )
    items = [UserProfile.model_validate(u) for u in users]
    pages_count = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, pages=pages_count
    )


@router.get("/users/{user_id}", response_model=UserProfile)
async def get_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
) -> UserProfile:
    """Admin-only: get a single user by ID."""
    user = await AdminService().get_user(db, user_id=user_id)
    return UserProfile.model_validate(user)


# ── User management ────────────────────────────────────────────────────
@router.post("/users/{user_id}/deactivate", status_code=status.HTTP_200_OK)
async def deactivate_user(
    user_id: uuid.UUID,
    request_data: AdminUserDeactivate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Admin deactivates (suspends) a member account."""
    await AdminService().deactivate_user(
        db, admin=current_user, target_user_id=user_id, reason=request_data.reason
    )
    return {"message": "User suspended successfully"}


@router.post("/users/{user_id}/reactivate", status_code=status.HTTP_200_OK)
async def reactivate_user(
    user_id: uuid.UUID,
    request_data: AdminUserReactivate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Admin reactivates a suspended member account."""
    await AdminService().reactivate_user(
        db, admin=current_user, target_user_id=user_id, reason=request_data.reason
    )
    return {"message": "User reactivated successfully"}


@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: uuid.UUID,
    request_data: AdminUserDelete,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Admin hard-deletes a user account."""
    await AdminService().delete_user(
        db, admin=current_user, target_user_id=user_id, reason=request_data.reason
    )
    return {"message": "User deleted successfully"}


# ── Member moderation profile (US29) ───────────────────────────────────
@router.get("/users/{user_id}/moderation")
async def get_user_moderation_profile(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Admin-only: view a member's moderation profile (US29).

    Returns the violation_count, damage_reported count, and the listing
    violation history (reports against their listings that were marked valid).
    """
    from sqlalchemy import select as _select

    from app.models.enums import ReportStatus
    from app.models.listing_report import ListingReport
    from app.models.tool import Tool

    user = await AdminService().get_user(db, user_id=user_id)

    # Get all VALID reports against this user's listings
    violation_reports = await db.execute(
        _select(ListingReport)
        .join(Tool, ListingReport.tool_id == Tool.id)
        .where(Tool.owner_id == user_id, ListingReport.status == ReportStatus.VALID)
        .order_by(ListingReport.created_at.desc())
    )
    reports = violation_reports.scalars().all()

    violation_history = [
        {
            "report_id": str(r.id),
            "tool_id": str(r.tool_id),
            "tool_name": r.tool.name if r.tool else None,
            "reason": r.reason.value if hasattr(r.reason, "value") else str(r.reason),
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "resolution_note": r.resolution_note,
        }
        for r in reports
    ]

    return {
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "status": user.status.value,
        "violation_count": user.violation_count,
        "damage_reported": user.damage_reported,
        "violation_history": violation_history,
    }


# ── Audit log ──────────────────────────────────────────────────────────
@router.get("/audit-log", response_model=PaginatedResponse[AuditLogResponse])
async def list_audit_log(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[User, Depends(get_current_admin_user)],
    actor_id: Annotated[
        uuid.UUID | None, Query(description="Filter by which admin performed the action")
    ] = None,
    action_type: Annotated[str | None, Query()] = None,
    target_type: Annotated[str | None, Query()] = None,
    target_id: Annotated[uuid.UUID | None, Query()] = None,
    date_from: Annotated[
        str | None, Query(description="ISO datetime lower bound (inclusive)")
    ] = None,
    date_to: Annotated[
        str | None, Query(description="ISO datetime upper bound (inclusive)")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[AuditLogResponse]:
    """Admin-only: query the moderation history / audit log (US32).

    Supports filtering by actor_id (acting admin), action_type,
    target_type, target_id, and a date range. Paginated 50/page default.
    """
    parsed_from = _parse_iso_datetime(date_from)
    parsed_to = _parse_iso_datetime(date_to, end_of_day=True)

    entries, total = await AdminService().list_audit_log(
        db,
        actor_id=actor_id,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        date_from=parsed_from,
        date_to=parsed_to,
        page=page,
        page_size=page_size,
    )
    items = [AuditLogResponse.model_validate(e) for e in entries]
    pages_count = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, pages=pages_count
    )


# ── Admin reservations overview (US34) ─────────────────────────────────
@router.get("/reservations", response_model=PaginatedResponse[ReservationResponse])
async def admin_list_all_reservations(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[User, Depends(get_current_admin_user)],
    state: Annotated[str | None, Query(description="Filter by reservation state")] = None,
    member_id: Annotated[uuid.UUID | None, Query()] = None,
    date_from: Annotated[
        str | None, Query(description="Start date lower bound (YYYY-MM-DD)")
    ] = None,
    date_to: Annotated[str | None, Query(description="Start date upper bound (YYYY-MM-DD)")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[ReservationResponse]:
    """Admin-only: list all reservations with filters (US34).

    Shows all active (REQUESTED, APPROVED, PICKED_UP) and historical
    reservations. Filterable by state, member (borrower or owner), and
    date range on start_date.
    """
    from datetime import date

    parsed_from = None
    try:
        if date_from:
            parsed_from = date.fromisoformat(date_from)
    except ValueError:
        raise ValidationError(
            f"Invalid date_from format: '{date_from}'. Use ISO date format"
        ) from None
    parsed_to = None
    try:
        if date_to:
            parsed_to = date.fromisoformat(date_to)
    except ValueError:
        raise ValidationError(f"Invalid date_to format: '{date_to}'. Use ISO date format") from None

    reservations, total = await AdminService().list_all_reservations(
        db,
        state=state,
        member_id=member_id,
        date_from=parsed_from,
        date_to=parsed_to,
        page=page,
        page_size=page_size,
    )
    items = [ReservationResponse.model_validate(r) for r in reservations]
    pages_count = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, pages=pages_count
    )


# -- Admin moderation reports (US33) ------------------------------------
@router.get("/reports/moderation")
async def generate_moderation_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[User, Depends(get_current_admin_user)],
    date_from: Annotated[
        str | None, Query(description="ISO datetime lower bound (inclusive)")
    ] = None,
    date_to: Annotated[
        str | None, Query(description="ISO datetime upper bound (inclusive)")
    ] = None,
) -> dict:
    """Admin-only: generate a community moderation report (US33).

    Returns aggregate totals (reports, suspensions, reactivations, tool
    deactivations, reservation activity) and the detailed audit log records
    for the given date range.
    """
    from app.services.admin_report import ModerationReportService

    parsed_from = _parse_iso_datetime(date_from)
    parsed_to = _parse_iso_datetime(date_to, end_of_day=True)

    service = ModerationReportService()
    report = await service.generate_report(
        db,
        date_from=parsed_from,
        date_to=parsed_to,
    )

    # Serialize audit log records for JSON response
    records_data = [
        {
            "id": str(r.id),
            "action_type": r.action_type,
            "target_type": r.target_type,
            "target_id": str(r.target_id),
            "reason": r.reason,
            "actor_id": str(r.actor_id) if r.actor_id else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in report["records"]
    ]

    return {
        "summary": report["summary"],
        "records": records_data,
        "report_type": "moderation",
        "date_from": parsed_from.isoformat() if parsed_from else None,
        "date_to": parsed_to.isoformat() if parsed_to else None,
    }


@router.get("/reports/moderation/export")
async def export_moderation_report_csv(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[User, Depends(get_current_admin_user)],
    date_from: Annotated[
        str | None, Query(description="ISO datetime lower bound (inclusive)")
    ] = None,
    date_to: Annotated[
        str | None, Query(description="ISO datetime upper bound (inclusive)")
    ] = None,
) -> dict:
    """Admin-only: export a community moderation report as CSV (US33 Scenario 2).

    Returns a JSON wrapper around the CSV text so the frontend can trigger
    a file download. The CSV includes column headers matching the report
    columns.
    """
    from app.services.admin_report import ModerationReportService

    parsed_from = _parse_iso_datetime(date_from)
    parsed_to = _parse_iso_datetime(date_to, end_of_day=True)

    service = ModerationReportService()
    report = await service.generate_report(
        db,
        date_from=parsed_from,
        date_to=parsed_to,
    )

    # Build CSV from the summary section
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Metric", "Value"])
    for key, value in report["summary"].items():
        writer.writerow([key, value])
    writer.writerow([])
    writer.writerow(["Audit Log Records"])
    writer.writerow(
        [
            "id",
            "action_type",
            "target_type",
            "target_id",
            "reason",
            "actor_id",
            "created_at",
        ]
    )
    for r in report["records"]:
        writer.writerow(
            [
                str(r.id),
                r.action_type,
                r.target_type,
                str(r.target_id),
                r.reason,
                str(r.actor_id) if r.actor_id else "",
                r.created_at.isoformat() if r.created_at else "",
            ]
        )

    csv_text = output.getvalue()
    return {
        "csv": csv_text,
        "filename": "moderation_report.csv",
        "content_type": "text/csv",
    }
