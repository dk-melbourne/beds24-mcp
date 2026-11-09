"""Server instructions, tool annotations and paging for calendar/property/availability tools."""

from typing import Any

import pytest

from src.server import SERVER_INSTRUCTIONS, create_server
from conftest import call

READS = ["get_calendar", "get_properties", "get_property_rooms", "check_availability", "get_best_price"]
WRITES = ["update_pricing", "set_availability", "block_dates"]


def test_instructions_cover_key_guidance() -> None:
    text = SERVER_INSTRUCTIONS.lower()
    assert "pricelabs" in text
    assert "include date_to" in text
    assert "truncated" in text
    assert "never deleted" in text
    assert 150 <= len(SERVER_INSTRUCTIONS.split()) <= 250


def test_server_uses_instructions() -> None:
    assert create_server().instructions == SERVER_INSTRUCTIONS


async def _annotations(mcp: Any) -> dict[str, Any]:
    return {t.name: t.annotations for t in await mcp.list_tools()}


async def test_read_tools_are_read_only(mcp: Any) -> None:
    annotations = await _annotations(mcp)
    for name in READS:
        assert annotations[name].read_only_hint is True, name
        assert annotations[name].open_world_hint is True, name


async def test_calendar_writes_are_destructive_and_idempotent(mcp: Any) -> None:
    annotations = await _annotations(mcp)
    for name in WRITES:
        a = annotations[name]
        assert (a.read_only_hint, a.destructive_hint, a.idempotent_hint, a.open_world_hint) == (
            False, True, True, True,
        ), name


async def test_update_pricing_docstring_mentions_pricelabs(mcp: Any) -> None:
    tool = next(t for t in await mcp.list_tools() if t.name == "update_pricing")
    assert "PriceLabs" in tool.description


def _page(rows: list[Any], more: bool) -> dict[str, Any]:
    return {"success": True, "data": rows, "pages": {"nextPageExists": more}}


async def test_get_properties_reads_all_pages(mcp: Any, beds24: Any) -> None:
    beds24.get_replies = [_page([{"id": 1}], True), _page([{"id": 2}], False)]
    result = await call(mcp, "get_properties", {})
    assert [p["id"] for p in result["data"]] == [1, 2]
    assert result["metadata"]["truncated"] is False
    assert [r["params"]["page"] for r in beds24.requests] == [1, 2]


async def test_get_properties_reports_truncation(mcp: Any, beds24: Any) -> None:
    beds24.get_reply = _page([{"id": 1}], True)
    result = await call(mcp, "get_properties", {})
    assert result["success"] is True
    assert result["metadata"]["truncated"] is True


async def test_get_calendar_pages_and_truncation(mcp: Any, beds24: Any) -> None:
    args = {"property_id": 1, "date_from": "2027-03-01", "date_to": "2027-03-03"}
    beds24.get_replies = [_page([{"roomId": 1}], True), _page([{"roomId": 2}], False)]
    result = await call(mcp, "get_calendar", args)
    assert len(result["data"]["data"]) == 2
    assert result["metadata"]["truncated"] is False

    beds24.get_reply = _page([{"roomId": 1}], True)
    result = await call(mcp, "get_calendar", args)
    assert result["metadata"]["truncated"] is True


@pytest.mark.parametrize("tool", ["check_availability", "get_best_price"])
async def test_offers_tools_page_and_report_truncation(mcp: Any, beds24: Any, tool: str) -> None:
    args = {"property_id": 1, "check_in": "2027-03-01", "check_out": "2027-03-03"}
    offer = {"offerId": 1, "price": 100, "currency": "AUD"}
    beds24.get_replies = [
        _page([{"roomId": 1, "offers": [offer]}], True),
        _page([{"roomId": 2, "offers": [{**offer, "price": 90}]}], False),
    ]
    result = await call(mcp, tool, args)
    assert result["metadata"]["truncated"] is False
    if tool == "get_best_price":
        assert result["data"]["room_id"] == 2
    else:
        assert len(result["data"]["rooms"]) == 2

    beds24.get_reply = _page([{"roomId": 1, "offers": [offer]}], True)
    result = await call(mcp, tool, args)
    assert result["metadata"]["truncated"] is True


@pytest.mark.parametrize("tool", ["get_calendar", "check_availability", "get_best_price"])
async def test_beds24_error_is_reported_not_treated_as_no_availability(mcp: Any, beds24: Any, tool: str) -> None:
    from conftest import TOOL_ARGS

    beds24.get_reply = {"success": False, "error": "boom"}
    result = await call(mcp, tool, TOOL_ARGS[tool])
    assert result["success"] is False
    assert "boom" in result["error"]
