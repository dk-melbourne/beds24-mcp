"""Every tool, run against fake Beds24 replies."""

from typing import Any

import pytest
from conftest import POST_OK, TOOL_ARGS, WRITE_TOOLS, call

from src.server import create_server


async def test_server_registers_every_tool() -> None:
    from fastmcp import Client

    async with Client(create_server()) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert names == set(TOOL_ARGS)


# Beds24 POST replies: (reply, should the tool report success?)
POST_REPLIES = {
    "confirmed": (POST_OK, True),
    "rejected": ([{"success": False, "errors": [{"field": "x", "message": "bad"}]}], False),
    "success flag but errors": ([{"success": True, "errors": [{"message": "bad"}]}], False),
    "empty list": ([], False),
    "single object, not a list": ({"success": True}, False),
}


@pytest.mark.parametrize("tool", WRITE_TOOLS)
@pytest.mark.parametrize("case", POST_REPLIES)
async def test_write_tool_trusts_only_a_confirmed_reply(mcp: Any, beds24: Any, tool: str, case: str) -> None:
    beds24.post_reply, should_succeed = POST_REPLIES[case]
    result = await call(mcp, tool, TOOL_ARGS[tool])
    assert result["success"] is should_succeed, result
    assert [r["method"] for r in beds24.requests] == ["post"], "expected exactly one write"


async def test_update_pricing_sends_price1_for_the_room_and_dates(mcp: Any, beds24: Any) -> None:
    await call(mcp, "update_pricing", TOOL_ARGS["update_pricing"])
    assert beds24.requests[0]["endpoint"] == "/inventory/rooms/calendar"
    assert beds24.requests[0]["body"] == [
        {"roomId": 560912, "calendar": [{"from": "2027-03-01", "to": "2027-03-03", "price1": 235}]}
    ]


@pytest.mark.parametrize(("tool", "num_avail"), [("set_availability", 1), ("block_dates", 0)])
async def test_availability_tools_send_num_avail(mcp: Any, beds24: Any, tool: str, num_avail: int) -> None:
    await call(mcp, tool, TOOL_ARGS[tool])
    assert beds24.requests[0]["body"][0]["calendar"][0]["numAvail"] == num_avail


async def test_create_booking_returns_new_booking_id(mcp: Any, beds24: Any) -> None:
    result = await call(mcp, "create_booking", TOOL_ARGS["create_booking"])
    assert result["data"]["new"]["id"] == 12345
    assert beds24.requests[0]["endpoint"] == "/bookings"


async def test_internal_note_is_sent_as_internal_note(mcp: Any, beds24: Any) -> None:
    await call(mcp, "add_internal_note", TOOL_ARGS["add_internal_note"])
    assert beds24.requests[0]["body"] == [
        {"bookingId": 111, "message": "Late check-in", "source": "internalNote"}
    ]


@pytest.mark.parametrize(
    "args",
    [
        {"arrival": "2027-03-03", "departure": "2027-03-01"},
        {"arrival": "03/01/2027"},
        {"num_adult": 0},
    ],
)
async def test_create_booking_rejects_bad_input_without_calling_beds24(
    mcp: Any, beds24: Any, args: dict[str, Any]
) -> None:
    result = await call(mcp, "create_booking", {**TOOL_ARGS["create_booking"], **args})
    assert result["success"] is False
    assert beds24.requests == []


@pytest.mark.parametrize("tool", [t for t in TOOL_ARGS if t not in WRITE_TOOLS])
async def test_read_tool_never_writes(mcp: Any, beds24: Any, tool: str) -> None:
    await call(mcp, tool, TOOL_ARGS[tool])
    assert beds24.requests, f"{tool} made no request"
    assert all(r["method"] == "get" for r in beds24.requests)


async def test_every_tool_declares_whether_it_writes() -> None:
    """Clients use these hints to ask the user before a write; write tools must not look read-only."""
    from fastmcp import Client

    async with Client(create_server()) as client:
        tools = {tool.name: tool.annotations for tool in await client.list_tools()}
    for name, hints in tools.items():
        assert hints is not None, f"{name} has no annotations"
        assert hints.read_only_hint is (name not in WRITE_TOOLS), f"{name} readOnlyHint is wrong"
        if name in WRITE_TOOLS:
            assert hints.destructive_hint is not None, f"{name} must set destructiveHint"
