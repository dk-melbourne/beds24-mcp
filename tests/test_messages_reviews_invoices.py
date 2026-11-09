"""Messages (paging, mark read), reviews and invoices."""

from typing import Any

import pytest
from conftest import POST_OK, call


READ_TOOLS = ["get_messages", "get_unread_messages", "get_reviews", "get_invoices"]
WRITE_NOT_IDEMPOTENT = ["send_message", "add_internal_note"]


def page(rows: list[Any], more: bool) -> dict[str, Any]:
    return {"success": True, "data": rows, "pages": {"nextPageExists": more}}


async def test_annotations(mcp: Any) -> None:
    tools = {t.name: t.annotations for t in await mcp.list_tools()}
    for name in READ_TOOLS:
        assert tools[name].read_only_hint is True, name
    for name in WRITE_NOT_IDEMPOTENT:
        a = tools[name]
        assert (a.read_only_hint, a.destructive_hint, a.idempotent_hint) == (False, False, False), name
    a = tools["mark_messages_read"]
    assert (a.read_only_hint, a.destructive_hint, a.idempotent_hint) == (False, False, True)


async def test_send_message_has_no_subject(mcp: Any, beds24: Any) -> None:
    await call(mcp, "send_message", {"booking_id": 111, "message": "Hi"})
    assert beds24.requests[0]["body"] == [{"bookingId": 111, "message": "Hi"}]
    tool = next(t for t in await mcp.list_tools() if t.name == "send_message")
    assert "subject" not in tool.input_schema["properties"]


@pytest.mark.parametrize("tool", ["get_messages", "get_unread_messages"])
async def test_messages_read_all_pages(mcp: Any, beds24: Any, tool: str) -> None:
    beds24.get_replies = [page([{"id": 1}], True), page([{"id": 2}], False)]
    result = await call(mcp, tool, {})
    assert [m["id"] for m in result["data"]] == [1, 2]
    assert result["metadata"]["truncated"] is False
    assert [r["params"]["page"] for r in beds24.requests] == [1, 2]


async def test_messages_report_truncation(mcp: Any, beds24: Any) -> None:
    beds24.get_replies = [page([{"id": n}], True) for n in range(10)]
    result = await call(mcp, "get_unread_messages", {})
    assert result["metadata"]["truncated"] is True
    assert result["metadata"]["count"] == 10


async def test_messages_error_passthrough(mcp: Any, beds24: Any) -> None:
    beds24.get_reply = {"success": False, "error": "nope"}
    result = await call(mcp, "get_messages", {})
    assert result == {"success": False, "error": "nope"}


async def test_mark_messages_read_body(mcp: Any, beds24: Any) -> None:
    beds24.post_reply = [POST_OK[0], POST_OK[0]]
    result = await call(mcp, "mark_messages_read", {"message_ids": [11, 12]})
    assert result["success"] is True
    assert beds24.requests[0]["body"] == [{"id": 11, "read": True}, {"id": 12, "read": True}]


async def test_mark_messages_read_reports_failed_ids(mcp: Any, beds24: Any) -> None:
    bad = {"success": False, "errors": [{"message": "x"}]}
    beds24.post_reply = [POST_OK[0], bad, POST_OK[0]]
    result = await call(mcp, "mark_messages_read", {"message_ids": [11, 12, 13]})
    assert result["success"] is False
    assert result["data"]["failed_ids"] == [12]


async def test_mark_messages_read_short_reply_counts_as_failed(mcp: Any, beds24: Any) -> None:
    beds24.post_reply = [POST_OK[0]]
    result = await call(mcp, "mark_messages_read", {"message_ids": [11, 12]})
    assert result["success"] is False
    assert result["data"]["failed_ids"] == [12]


async def test_mark_messages_read_rejects_empty(mcp: Any, beds24: Any) -> None:
    result = await call(mcp, "mark_messages_read", {"message_ids": []})
    assert result["success"] is False
    assert beds24.requests == []


async def test_reviews_airbnb_request(mcp: Any, beds24: Any) -> None:
    beds24.get_reply = {"success": True, "data": [{"id": "r1"}]}
    result = await call(mcp, "get_reviews", {"channel": "airbnb", "room_id": 560912})
    assert beds24.requests == [
        {"method": "get", "endpoint": "/channels/airbnb/reviews", "params": {"roomId": 560912}}
    ]
    assert result["data"] == [{"id": "r1"}]


async def test_reviews_booking_request(mcp: Any, beds24: Any) -> None:
    await call(mcp, "get_reviews", {"channel": "booking", "property_id": 5, "from_date": "2027-01-01"})
    assert beds24.requests == [
        {
            "method": "get",
            "endpoint": "/channels/booking/reviews",
            "params": {"propertyId": 5, "from": "2027-01-01"},
        }
    ]


@pytest.mark.parametrize(
    "args",
    [
        {"channel": "airbnb"},
        {"channel": "airbnb", "room_id": 1, "property_id": 2},
        {"channel": "airbnb", "room_id": 1, "from_date": "2027-01-01"},
        {"channel": "booking", "from_date": "2027-01-01"},
        {"channel": "booking", "property_id": 2},
        {"channel": "booking", "property_id": 2, "from_date": "01/02/2027"},
        {"channel": "booking", "property_id": 2, "from_date": "2027-01-01", "room_id": 1},
    ],
)
async def test_reviews_reject_bad_input_without_calling_beds24(mcp: Any, beds24: Any, args: dict[str, Any]) -> None:
    result = await call(mcp, "get_reviews", args)
    assert result["success"] is False
    assert beds24.requests == []


async def test_reviews_reject_unknown_channel(mcp: Any, beds24: Any) -> None:
    result = await mcp.call_tool("get_reviews", {"channel": "vrbo", "room_id": 1}, raise_on_error=False)
    assert result.is_error
    assert beds24.requests == []


async def test_invoices_pages_and_truncation(mcp: Any, beds24: Any) -> None:
    beds24.get_replies = [page([{"invoiceId": 1}], True), page([{"invoiceId": 2}], False)]
    result = await call(mcp, "get_invoices", {"booking_id": 111})
    assert [i["invoiceId"] for i in result["data"]] == [1, 2]
    assert result["metadata"]["truncated"] is False
    assert all(r["endpoint"] == "/bookings/invoices" and r["params"]["bookingId"] == 111 for r in beds24.requests)
