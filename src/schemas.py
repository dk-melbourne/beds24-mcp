"""
Pydantic Schemas
~~~~~~~~~~~~~~~~

Input and output schemas for MCP tool arguments and responses.
These schemas provide validation and type safety for all tool interactions.
"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Base Schemas
# ============================================================================


class ToolResponse(BaseModel):
    """Base response schema for all MCP tools."""

    success: bool = Field(description="Whether the operation succeeded")
    data: Any | None = Field(default=None, description="Response data")
    error: str | None = Field(default=None, description="Error message if failed")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (cache status, timing, etc.)",
    )


# ============================================================================
# Beds24 Tool Schemas
# ============================================================================

# Bookings
# --------


class GetBookingsParams(BaseModel):
    """Parameters for get_bookings tool."""

    arrival_from: date | None = Field(default=None, description="Filter by arrival date from")
    arrival_to: date | None = Field(default=None, description="Filter by arrival date to")
    departure_from: date | None = Field(default=None, description="Filter by departure date from")
    departure_to: date | None = Field(default=None, description="Filter by departure date to")
    property_id: int | None = Field(default=None, description="Filter by property ID")
    room_id: int | None = Field(default=None, description="Filter by room ID")
    status: str | None = Field(default=None, description="Filter by booking status")


class GetBookingParams(BaseModel):
    """Parameters for get_booking tool."""

    booking_id: int = Field(description="Beds24 booking ID")


class SearchBookingsParams(BaseModel):
    """Parameters for search_bookings tool."""

    guest_name: str | None = Field(default=None, description="Guest name to search")
    email: str | None = Field(default=None, description="Guest email to search")
    booking_reference: str | None = Field(default=None, description="Booking reference")
    date_from: date | None = Field(default=None, description="Search from date")
    date_to: date | None = Field(default=None, description="Search to date")


# Properties
# ----------


class GetPropertyRoomsParams(BaseModel):
    """Parameters for get_property_rooms tool."""

    property_id: int = Field(description="Beds24 property ID")


# Availability
# ------------


class CheckAvailabilityParams(BaseModel):
    """Parameters for check_availability tool."""

    property_id: int = Field(description="Property ID")
    room_id: int | None = Field(default=None, description="Specific room ID (optional)")
    check_in: date = Field(description="Check-in date")
    check_out: date = Field(description="Check-out date")
    num_adults: int = Field(default=2, description="Number of adults")
    num_children: int = Field(default=0, description="Number of children")


class GetBestPriceParams(BaseModel):
    """Parameters for get_best_price tool."""

    property_id: int = Field(description="Property ID")
    check_in: date = Field(description="Check-in date")
    check_out: date = Field(description="Check-out date")
    num_adults: int = Field(default=2, description="Number of adults")
    num_children: int = Field(default=0, description="Number of children")


# Messages
# --------


class GetMessagesParams(BaseModel):
    """Parameters for get_messages tool."""

    booking_id: int | None = Field(default=None, description="Filter by booking ID")
    unread_only: bool = Field(default=False, description="Show only unread messages")
    date_from: date | None = Field(default=None, description="Filter from date")


class SendMessageParams(BaseModel):
    """Parameters for send_message tool."""

    booking_id: int = Field(description="Booking ID to send message to")
    message: str = Field(description="Message content")
    subject: str | None = Field(default=None, description="Message subject (optional)")


class AddInternalNoteParams(BaseModel):
    """Parameters for add_internal_note tool."""

    booking_id: int = Field(description="Booking ID")
    note: str = Field(description="Internal note content")


# Calendar
# --------


class GetCalendarParams(BaseModel):
    """Parameters for get_calendar tool."""

    property_id: int = Field(description="Property ID")
    room_id: int | None = Field(default=None, description="Room ID (optional)")
    date_from: date = Field(description="Start date")
    date_to: date = Field(description="End date")


class UpdatePricingParams(BaseModel):
    """Parameters for update_pricing tool."""

    property_id: int = Field(description="Property ID")
    room_id: int = Field(description="Room ID")
    date_from: date = Field(description="Start date")
    date_to: date = Field(description="End date")
    price: float = Field(description="Nightly rate", gt=0)


class SetAvailabilityParams(BaseModel):
    """Parameters for set_availability tool."""

    property_id: int = Field(description="Property ID")
    room_id: int = Field(description="Room ID")
    date_from: date = Field(description="Start date")
    date_to: date = Field(description="End date")
    available: int = Field(description="Number of units available", ge=0)


class BlockDatesParams(BaseModel):
    """Parameters for block_dates tool."""

    property_id: int = Field(description="Property ID")
    room_id: int = Field(description="Room ID")
    date_from: date = Field(description="Start date")
    date_to: date = Field(description="End date")
    reason: str | None = Field(default=None, description="Blocking reason")
