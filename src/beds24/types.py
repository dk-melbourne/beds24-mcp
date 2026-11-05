"""
Beds24 Type Definitions
~~~~~~~~~~~~~~~~~~~~~~~

Pydantic models for all Beds24 API request and response structures.
Provides type safety and automatic validation for API interactions.

Models organized by domain:
- Authentication
- Common API Response Types
- Bookings
- Properties & Rooms
- Availability & Pricing
- Messages
- Calendar

These types match the TypeScript definitions in the reference implementation.
"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ============================================================================
# Authentication Types
# ============================================================================


class TokenResponse(BaseModel):
    """OAuth token response from Beds24."""

    token: str = Field(description="Access token for API requests")
    expiresIn: int = Field(description="Token lifetime in seconds")  # camelCase from API
    refreshToken: str = Field(description="Refresh token for obtaining new access tokens")


class TokenDetails(BaseModel):
    """Token details with expiry tracking (internal)."""

    token: str
    expires_at: datetime
    refresh_token: str


# ============================================================================
# Common API Response Types
# ============================================================================


class ApiResponsePages(BaseModel):
    """Pagination info from API response."""

    page: int
    perPage: int
    totalPages: int


class SuccessfulApiResponse(BaseModel):
    """Successful API response wrapper."""

    success: bool = Field(default=True)
    type: str | None = None
    pages: ApiResponsePages | None = None
    data: Any = None


class UnsuccessfulApiResponse(BaseModel):
    """Unsuccessful API response."""

    success: bool = Field(default=False)
    error: str | None = None
    message: str | None = None


# ============================================================================
# Rate Limiting Headers
# ============================================================================


class RateLimitHeaders(BaseModel):
    """Rate limit headers from Beds24 API."""

    X_FiveMinCreditLimit: str | None = Field(None, alias="X-FiveMinCreditLimit")
    X_FiveMinCreditLimit_ResetsIn: str | None = Field(None, alias="X-FiveMinCreditLimit-ResetsIn")
    X_FiveMinCreditLimit_Remaining: str | None = Field(None, alias="X-FiveMinCreditLimit-Remaining")
    X_RequestCost: str | None = Field(None, alias="X-RequestCost")


# ============================================================================
# Booking Types
# ============================================================================


BookingStatus = Literal["confirmed", "request", "new", "cancelled", "black", "inquiry"]


class InvoiceItem(BaseModel):
    """Booking invoice line item."""

    id: int | None = None
    type: str
    qty: int
    amount: float
    description: str | None = None


class InfoItem(BaseModel):
    """Booking information item."""

    id: int | None = None
    code: str
    text: str


class BookingGroup(BaseModel):
    """Booking group information (for multi-room bookings)."""

    masterId: int
    bookingIds: list[int]


class Booking(BaseModel):
    """Complete booking model matching Beds24 API."""

    id: int | None = Field(None, description="Booking ID (omit for creation)")
    masterId: int | None = Field(None, description="Master booking ID for grouped bookings")
    propertyId: int = Field(description="Property ID")
    roomId: int = Field(description="Room ID")
    unitId: int | None = Field(None, description="Specific unit ID")
    status: BookingStatus = Field(description="Booking status")
    arrival: str = Field(description="Arrival date (YYYY-MM-DD)")
    departure: str = Field(description="Departure date (YYYY-MM-DD)")
    numAdult: int = Field(description="Number of adults")
    numChild: int | None = Field(None, description="Number of children")

    # Guest information
    title: str | None = None
    firstName: str
    lastName: str
    email: str
    mobile: str | int | None = None
    phone: str | int | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    postcode: str | None = None
    country: str | None = None
    country2: str | None = Field(None, description="Alternative country code")

    # Timestamps
    bookingTime: str | None = Field(None, description="ISO datetime when booking was created")
    modifiedTime: str | None = Field(None, description="ISO datetime when last modified")

    # Channel and reference
    channel: str | None = Field(None, description="Booking channel (Direct, Airbnb, Booking.com, etc.)")
    apiReference: str | None = Field(None, description="External reference/confirmation code")
    comment: str | None = Field(None, description="Booking comments/notes")

    # Pricing and offers
    offerId: int | None = None
    roomQty: int | None = Field(None, description="Number of rooms")
    subStatus: str | None = None

    # Additional data
    invoiceItems: list[InvoiceItem] | None = Field(None, description="Invoice line items")
    infoItems: list[InfoItem] | None = Field(None, description="Additional booking info")
    bookingGroup: BookingGroup | None = None


class BookingQueryParams(BaseModel):
    """Parameters for querying bookings."""

    propertyId: int | None = None
    roomId: int | None = None
    id: int | None = None
    masterId: int | None = None
    apiReference: str | None = None
    channel: str | None = None

    # Date filters
    arrival: str | None = Field(None, description="Exact arrival date (YYYY-MM-DD)")
    departure: str | None = Field(None, description="Exact departure date (YYYY-MM-DD)")
    arrivalFrom: str | None = None
    arrivalTo: str | None = None
    departureFrom: str | None = None
    departureTo: str | None = None
    bookingFrom: str | None = None
    bookingTo: str | None = None
    modifiedFrom: str | None = None
    modifiedTo: str | None = None

    # Search and filters
    searchString: str | None = None
    filter: Literal["arrivals", "departures", "new", "current"] | None = None

    # Pagination and includes
    page: int | None = None
    includeInvoiceItems: bool | None = None
    includeInfoItems: bool | None = None
    includeGuests: bool | None = None
    includeBookingGroup: bool | None = None


# ============================================================================
# Message Types
# ============================================================================


MessageSource = Literal["host", "guest", "internalNote", "system"]


class Message(BaseModel):
    """Beds24 message model."""

    id: int | None = None
    bookingId: int
    propertyId: int | None = None
    roomId: int | None = None
    masterId: int | None = None
    message: str
    read: bool | None = None
    source: MessageSource | None = None
    attachment: str | None = Field(None, description="Base64 encoded attachment")
    attachmentName: str | None = None
    attachmentMimeType: str | None = None
    time: str | None = Field(None, description="ISO datetime")


class MessageQueryParams(BaseModel):
    """Parameters for querying messages."""

    messageId: int | None = None
    propertyId: int | None = None
    roomId: int | None = None
    bookingId: int | None = None
    masterId: int | None = None
    maxAge: int | None = Field(None, description="Maximum age in days (1-999)", ge=1, le=999)
    source: MessageSource | None = None
    read: bool | None = None


# ============================================================================
# Property Types
# ============================================================================


class PropertyText(BaseModel):
    """Property or room text in specific language."""

    lang: str | None = None
    name: str | None = None
    description: str | None = None


class PropertyPicture(BaseModel):
    """Property or room picture."""

    url: str
    caption: str | None = None
    order: int | None = None


class PropertyOffer(BaseModel):
    """Property offer/package."""

    id: int
    name: str
    description: str | None = None


class PriceRule(BaseModel):
    """Pricing rule."""

    id: int
    name: str
    description: str | None = None


class UpsellItem(BaseModel):
    """Upsell/extra item."""

    id: int
    name: str
    description: str | None = None
    price: float | None = None


class RoomUnit(BaseModel):
    """Individual room unit."""

    id: int
    name: str | None = None


class Room(BaseModel):
    """Room type definition."""

    id: int
    propertyId: int
    name: str
    qty: int | None = Field(None, description="Number of units")
    maxAdult: int | None = None
    maxChildren: int | None = None
    units: list[RoomUnit] | None = None
    offers: list[PropertyOffer] | None = None
    texts: list[PropertyText] | None = None
    pictures: list[PropertyPicture] | None = None
    priceRules: list[PriceRule] | None = None
    cancellationPolicy: str | None = Field(None, description="noRefund, flexible, etc.")

    # Special field with non-standard name
    class Config:
        fields = {"seven_day_discount_percent": "7DayDiscountPercent"}

    seven_day_discount_percent: float | None = None


class Property(BaseModel):
    """Property definition."""

    id: int
    name: str
    propertyType: str | None = Field(None, description="apartment, house, etc.")
    currency: str = Field(description="USD, EUR, etc.")
    address: str | None = None
    city: str | None = None
    state: str | None = None
    postcode: str | None = None
    country: str | None = None
    mobile: str | None = None
    email: str | None = None
    roomTypes: list[Room] | None = None
    texts: list[PropertyText] | None = None
    pictures: list[PropertyPicture] | None = None
    offers: list[PropertyOffer] | None = None
    priceRules: list[PriceRule] | None = None
    upsellItems: list[UpsellItem] | None = None


class PropertyQueryParams(BaseModel):
    """Parameters for querying properties."""

    id: int | None = None
    includeAllRooms: bool | None = None
    subAccounts: bool | None = None
    usage: bool | None = None
    languages: bool | None = None
    texts: bool | None = None
    pictures: bool | None = None
    offers: bool | None = None
    priceRules: bool | None = None
    upsellItems: bool | None = None
    rooms: bool | None = None
    unitDetails: bool | None = None


# ============================================================================
# Availability and Calendar Types
# ============================================================================


class AvailabilityOffer(BaseModel):
    """Availability offer for specific dates."""

    offerId: int
    roomName: str
    price: float
    currency: str
    numNights: int
    minStay: int | None = None
    maxStay: int | None = None


class RoomOffer(BaseModel):
    """Room offers for availability query."""

    roomId: int
    propertyId: int
    offers: list[AvailabilityOffer]


class OfferQueryParams(BaseModel):
    """Parameters for querying availability offers."""

    arrival: str = Field(description="Arrival date (YYYY-MM-DD)")
    departure: str = Field(description="Departure date (YYYY-MM-DD)")
    numAdults: int
    numChildren: int | None = None
    includeTexts: bool | None = None
    agentCode: str | None = None
    roomId: int | None = None
    propertyId: int | None = None


class CalendarEntry(BaseModel):
    """Calendar entry for updating/querying room calendar."""

    roomId: int | None = None
    propertyId: int | None = None
    from_date: str = Field(alias="from", description="Start date (YYYY-MM-DD)")
    to: str = Field(description="End date (YYYY-MM-DD)")
    numAvail: int | None = Field(None, description="Number available")
    minStay: int | None = None
    maxStay: int | None = None
    override: str | None = Field(None, description="blackout, open, etc.")
    price1: float | None = None
    price2: float | None = None
    price3: float | None = None
    price4: float | None = None
    price5: float | None = None
    multiplier: float | None = None
    channels: dict[str, Any] | None = None

    class Config:
        populate_by_name = True


class CalendarQueryParams(BaseModel):
    """Parameters for querying calendar data."""

    roomId: int | None = None
    propertyId: int | None = None
    startDate: str | None = None
    endDate: str | None = None
    numAvail: bool | None = None
    minStay: bool | None = None
    maxStay: bool | None = None
    multiplier: bool | None = None
    override: bool | None = None
    prices: bool | None = None
    channels: bool | None = None


# ============================================================================
# Configuration Types
# ============================================================================


class Beds24Config(BaseModel):
    """Configuration for Beds24 client."""

    inviteCode: str | None = Field(None, description="One-time invite code for setup")
    refreshToken: str | None = Field(None, description="Stored refresh token")
    baseUrl: str = Field(default="https://beds24.com/api/v2")


# ============================================================================
# Request Queue Types (Internal)
# ============================================================================


# These are not Pydantic models as they're internal to the client
# QueuedRequest is defined in client.py
