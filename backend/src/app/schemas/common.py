"""Common response schemas."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


def validate_full_name(v: str | None) -> str | None:
    """Validate a display name: strip whitespace, reject blank or overlong."""
    if v is not None:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Display name cannot be empty or whitespace-only")
        if len(stripped) > 40:
            raise ValueError("Display name must be 40 characters or fewer")
        return stripped
    return v


class MessageResponse(BaseModel):
    """Generic success message response."""

    message: str


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response.

    Shared contract for every list endpoint. The generic parameter ``T`` is
    resolved at usage site (e.g. ``PaginatedResponse[ToolResponse]``).
    """

    model_config = ConfigDict(from_attributes=True)

    items: list[T]  #: List of items for the current page.
    total: int  #: Total number of items matching the query (across all pages).
    page: int  #: Current page number (1-indexed).
    page_size: int  #: Number of items per page.
    pages: int  #: Total number of pages (``ceil(total / page_size)``).
