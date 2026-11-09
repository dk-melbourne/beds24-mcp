"""Booking tools: paging, modified filters, create/update/cancel request bodies and annotations."""

from typing import Any

import pytest
from conftest import POST_OK, TOOL_ARGS, call
from test_api_spec import spec  # noqa: F401  (fixture)

import src.server as server

READ_TOOLS = ["get_bookings", "get_booking", "get_arrivals", "get_departures", "search_bookings"]
PAGED_TOOLS = ["get_bookings", "get_arrivals", "get_departures", "search_bookings"]
BOOKING_WRITES = {"create_booking": (False, False), "update_booking": (True, False), "cancel_booking": (True, True)}


def page(rows: list[Any], more: bool) -> dict[str, Any]:
    return {"success": True, "data": rows, "pages": {"nextPageExists": more}}


@pytest.mark.parametrize("tool", PAGED_TOOLS)
async def test_list_tools_read_every_page(mcp: Any, beds24: Any, tool: str) -> None:
    beds24.get_replies = [page([{"id": 1}], True), page([{"id": 2}], False)]
    result = await call(mcp, tool, TOOL_ARGS[tool])
    assert [b["id"] for b in result["data"]] == [1, 2]
    assert [r["params"]["page"] for r in beds24.requests] == [1, 2]
    assert result["metadata"]["truncated"] is False


@pytest.mark.parametrize("tool", PAGED_TOOLS)
async def test_list_tools_report_truncation(mcp: Any, beds24: Any, tool: str) -> None:
    beds24.get_reply = page([{"id": 1}], True)
    result = await call(mcp, tool, TOOL_ARGS[tool])
    assert result["success"] is True
    assert result["metadata"]["truncated"] is True


async def test_get_bookings_sends_modified_filters(mcp: Any, beds24: Any) -> None:
    await call(mcp, "get_bookings", TOOL_ARGS["get_bookings"])
    params = beds24.requests[0]["params"]
    assert params["modifiedFrom"] == "2027-01-01T00:00:00"
    assert params["modifiedTo"] == "2027-03-01T12:30:00"


@pytest.mark.parametrize("field", ["modified_from", "modified_to"])
async def test_get_bookings_rejects_bad_modified_format(mcp: Any, beds24: Any, field: str) -> None:
    result = await call(mcp, "get_bookings", {field: "2027-01-01"})
    assert result["success"] is False
    assert beds24.requests == []


async def test_create_booking_sends_only_spec_fields(mcp: Any, beds24: Any) -> None:
    await call(mcp, "create_booking", TOOL_ARGS["create_booking"])
    body = beds24.requests[0]["body"][0]
    assert body["roomId"] == 560912
    assert body["notes"] == "test"
    for unwanted in ("propertyId", "channel", "apiReference", "comment"):
        assert unwanted not in body


async def test_update_booking_sends_id_and_only_given_fields(mcp: Any, beds24: Any) -> None:
    result = await call(mcp, "update_booking", {"booking_id": 111, "flag_text": "VIP", "num_child": 0})
    assert result["success"] is True
    assert beds24.requests[0]["endpoint"] == "/bookings"
    assert beds24.requests[0]["body"] == [{"id": 111, "flagText": "VIP", "numChild": 0}]


async def test_update_booking_can_clear_flag_color(mcp: Any, beds24: Any) -> None:
    await call(mcp, "update_booking", {"booking_id": 111, "flag_color": ""})
    assert beds24.requests[0]["body"] == [{"id": 111, "flagColor": ""}]


async def test_update_booking_never_sends_status(mcp: Any, beds24: Any) -> None:
    await call(mcp, "update_booking", TOOL_ARGS["update_booking"])
    assert "status" not in beds24.requests[0]["body"][0]


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"arrival": "03/01/2027"},
        {"departure": "2027-02-30"},
        {"arrival": "2027-03-05", "departure": "2027-03-05"},
        {"num_adult": 0},
        {"num_child": -1},
    ],
)
async def test_update_booking_rejects_bad_input_without_calling_beds24(
    mcp: Any, beds24: Any, args: dict[str, Any]
) -> None:
    result = await call(mcp, "update_booking", {"booking_id": 111, **args})
    assert result["success"] is False
    assert beds24.requests == []


async def test_cancel_booking_sets_status_only(mcp: Any, beds24: Any) -> None:
    result = await call(mcp, "cancel_booking", {"booking_id": 111})
    assert result["success"] is True
    assert beds24.requests == [
        {"method": "post", "endpoint": "/bookings", "body": [{"id": 111, "status": "cancelled"}]}
    ]


@pytest.mark.parametrize("tool", ["create_booking", "update_booking", "cancel_booking"])
async def test_booking_writes_invalidate_caches_only_when_confirmed(
    mcp: Any, beds24: Any, monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(server.resources.cache_manager, "invalidate_bookings", lambda: calls.append(1))

    beds24.post_reply = [{"success": False, "errors": [{"message": "bad"}]}]
    await call(mcp, tool, TOOL_ARGS[tool])
    assert calls == []

    beds24.post_reply = POST_OK
    await call(mcp, tool, TOOL_ARGS[tool])
    assert calls == [1]


async def test_booking_tool_annotations(mcp: Any) -> None:
    tools = {t.name: t.annotations for t in await mcp.list_tools()}
    for name in READ_TOOLS:
        assert tools[name].read_only_hint is True
    for name, (destructive, idempotent) in BOOKING_WRITES.items():
        assert tools[name].read_only_hint is False
        assert tools[name].destructive_hint is destructive
        assert tools[name].idempotent_hint is idempotent


@pytest.mark.parametrize("tool", ["update_booking", "cancel_booking"])
async def test_partial_update_fields_are_defined_by_the_spec(
    mcp: Any, beds24: Any, spec: dict[str, Any], tool: str  # noqa: F811
) -> None:
    await call(mcp, tool, TOOL_ARGS[tool])
    defined = set(spec["components"]["schemas"]["newBooking"]["properties"]) | {"id"}
    assert set(beds24.requests[0]["body"][0]) <= defined


@pytest.mark.parametrize("tool", ["create_booking", "update_booking", "cancel_booking"])
async def test_booking_writes_clear_cached_calendar_and_availability(
    mcp: Any, beds24: Any, monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    import src.server as server

    cleared: list[str] = []
    cache = server.resources.cache_manager
    for name in ("invalidate_bookings", "invalidate_calendar", "invalidate_availability"):
        monkeypatch.setattr(cache, name, lambda name=name: cleared.append(name))
    result = await call(mcp, tool, TOOL_ARGS[tool])
    assert result["success"] is True
    assert set(cleared) == {"invalidate_bookings", "invalidate_calendar", "invalidate_availability"}
