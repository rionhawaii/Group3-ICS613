"""PostgreSQL-native ENUM definitions used across models."""

import enum


class UserStatus(enum.Enum):
    EMAIL_PENDING = "EMAIL_PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class InviteStatus(enum.Enum):
    SENT = "sent"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ToolCondition(enum.Enum):
    NEW = "NEW"
    LIKE_NEW = "LIKE_NEW"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


class ReservationState(enum.Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    PICKED_UP = "PICKED_UP"
    RETURNED = "RETURNED"
    DENIED = "DENIED"
    CANCELLED = "CANCELLED"


class CancellerType(enum.Enum):
    """Who cancelled a reservation.

    Stored as a free-form string at the DB level (with a CHECK constraint
    to reject anything else) so we can add new values without an Alembic
    migration. Used in ``Reservation.cancelled_by_type``.
    """

    BORROWER = "borrower"
    OWNER = "owner"
    SYSTEM = "system"
    ADMIN = "admin"


class DeactivationActor(enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    DAMAGE_REPORT = "DAMAGE_REPORT"


class ReportStatus(enum.Enum):
    PENDING = "PENDING"
    VALID = "VALID"
    INVALID = "INVALID"


class ReportReason(enum.Enum):
    """Predefined reason selector values for listing reports (US26)."""

    INAPPROPRIATE_CONTENT = "INAPPROPRIATE_CONTENT"
    PROHIBITED_ITEM = "PROHIBITED_ITEM"
    MISLEADING_LISTING = "MISLEADING_LISTING"
    SCAM_OR_FRAUD = "SCAM_OR_FRAUD"
    DUPLICATE_LISTING = "DUPLICATE_LISTING"
    OTHER = "OTHER"


class SuspensionAction(enum.Enum):
    SUSPEND = "SUSPEND"
    REACTIVATE = "REACTIVATE"


class NotificationType(enum.Enum):
    INVITE_SENT = "INVITE_SENT"
    EMAIL_VERIFIED = "EMAIL_VERIFIED"
    PASSWORD_RESET = "PASSWORD_RESET"
    RESERVATION_REQUESTED = "RESERVATION_REQUESTED"
    RESERVATION_APPROVED = "RESERVATION_APPROVED"
    RESERVATION_DENIED = "RESERVATION_DENIED"
    RESERVATION_CANCELLED = "RESERVATION_CANCELLED"
    RESERVATION_PICKED_UP = "RESERVATION_PICKED_UP"
    RESERVATION_RETURNED = "RESERVATION_RETURNED"
    RESERVATION_OVERDUE = "RESERVATION_OVERDUE"
    RESERVATION_OVERDUE_ADMIN_ALERT = "RESERVATION_OVERDUE_ADMIN_ALERT"
    TOOL_DEACTIVATED = "TOOL_DEACTIVATED"
    TOOL_REACTIVATED = "TOOL_REACTIVATED"
    ACCOUNT_SUSPENDED = "ACCOUNT_SUSPENDED"
    ACCOUNT_REACTIVATED = "ACCOUNT_REACTIVATED"
    LISTING_REPORT_SUBMITTED = "LISTING_REPORT_SUBMITTED"
    LISTING_REPORT_RESOLVED = "LISTING_REPORT_RESOLVED"
