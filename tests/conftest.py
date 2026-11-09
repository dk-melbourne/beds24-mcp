"""Shared test setup: run the real tools against a fake Beds24 client (no network, no token)."""

import os

os.environ.setdefault("BEDS24_REFRESH_TOKEN", "test-token")

from types import SimpleNamespace  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from fastmcp import Client, FastMCP  # noqa: E402

import src.server as server  # noqa: E402
from src.beds24.cache import CacheManager  # noqa: E402
from src.beds24.registry import register_beds24_tools  # noqa: E402

# A successful reply from a Beds24 POST endpoint: a list with one result per item sent.
POST_OK = [{"success": True, "new": {"id": 12345}}]


class FakeBeds24Client:
    """Stands in for Beds24Client: records every request and returns a canned reply."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.get_reply: Any = {"success": True, "data": []}
        # If set, each GET returns the next reply in this list (e.g. one per page).
        self.get_replies: list[Any] = []
        self.post_reply: Any = POST_OK

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        self.requests.append({"method": "get", "endpoint": endpoint, "params": params or {}})
        if self.get_replies:
            return self.get_replies.pop(0)
        return self.get_reply

    async def post(self, endpoint: str, json: Any = None) -> Any:
        self.requests.append({"method": "post", "endpoint": endpoint, "body": json})
        return self.post_reply


@pytest.fixture
def beds24(monkeypatch: pytest.MonkeyPatch) -> FakeBeds24Client:
    fake = FakeBeds24Client()
    resources = SimpleNamespace(
        beds24_client=fake,
        cache_manager=CacheManager(enabled=False),
        auth_manager=None,
    )
    monkeypatch.setattr(server, "resources", resources)
    return fake


@pytest.fixture
async def mcp(beds24: FakeBeds24Client) -> Any:
    app = FastMCP("beds24-test")
    register_beds24_tools(app, None)
    async with Client(app) as client:
        yield client


async def call(mcp: Client, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call a tool and return its result dict."""
    result = await mcp.call_tool(tool, args, raise_on_error=False)
    assert not result.is_error, f"{tool} raised: {result.content}"
    return result.structured_content


# Example arguments for every tool, using every optional argument, so tests see every field sent.
ROOM = {"property_id": 267799, "room_id": 560912}
DATES = {"date_from": "2027-03-01", "date_to": "2027-03-03"}
STAY = {"property_id": 267799, "check_in": "2027-03-01", "check_out": "2027-03-03"}
TOOL_ARGS: dict[str, dict[str, Any]] = {
    "get_properties": {},
    "get_property_rooms": {"property_id": 267799},
    "get_calendar": {"property_id": 267799, "room_id": 560912, **DATES},
    "update_pricing": {**ROOM, **DATES, "price": 235},
    "set_availability": {**ROOM, **DATES, "available": 1},
    "block_dates": {**ROOM, **DATES, "reason": "maintenance"},
    "check_availability": {**STAY, "num_adults": 2, "num_children": 1, "room_id": 560912},
    "get_best_price": {**STAY, "num_adults": 2, "num_children": 1},
    "get_bookings": {
        "arrival_from": "2027-03-01", "arrival_to": "2027-03-31",
        "departure_from": "2027-03-01", "departure_to": "2027-03-31",
        "property_id": 267799, "room_id": 560912, "status": "confirmed", "search_string": "Smith",
        "modified_from": "2027-01-01T00:00:00", "modified_to": "2027-03-01T12:30:00",
    },
    "get_booking": {"booking_id": 111},
    "search_bookings": {"search_string": "Smith", "property_id": 267799},
    "get_arrivals": {"arrival_from": "2027-03-01", "arrival_to": "2027-03-02", "property_id": 267799},
    "get_departures": {
        "departure_from": "2027-03-01", "departure_to": "2027-03-02", "property_id": 267799,
    },
    "create_booking": {
        "room_id": 560912, "status": "confirmed", "arrival": "2027-03-01", "departure": "2027-03-03",
        "num_adult": 2, "first_name": "Test", "last_name": "Guest", "email": "guest@example.com",
        "num_child": 1, "title": "Mr", "mobile": "0400000000", "phone": "0390000000",
        "address": "1 Test St", "city": "Melbourne", "state": "VIC", "postcode": "3000",
        "country": "AU", "comment": "test",
    },
    "get_messages": {"booking_id": 111, "unread_only": True, "date_from": "2027-03-01"},
    "get_unread_messages": {},
    "send_message": {"booking_id": 111, "message": "Hello"},
    "add_internal_note": {"booking_id": 111, "note": "Late check-in"},
    # Messages, reviews and invoices
    "mark_messages_read": {"message_ids": [11]},
    "get_reviews": {"channel": "booking", "property_id": 267799, "from_date": "2027-01-01"},
    "get_invoices": {"booking_id": 111},
    # Bookings
    "update_booking": {
        "booking_id": 111, "arrival": "2027-03-02", "departure": "2027-03-04", "num_adult": 2,
        "num_child": 1, "arrival_time": "15:00", "first_name": "New", "last_name": "Name",
        "email": "new@example.com", "phone": "0390000000", "mobile": "0400000000",
        "notes": "replaced", "flag_color": "ff0000", "flag_text": "VIP",
    },
    "cancel_booking": {"booking_id": 111},
}
WRITE_TOOLS = [
    "update_pricing", "set_availability", "block_dates",
    "create_booking", "send_message", "add_internal_note",
    "mark_messages_read", "update_booking", "cancel_booking",
]
