"""set_stay_restrictions and the calendar fields it changes."""

from datetime import datetime, timedelta
from typing import Any

import pytest
from conftest import ROOM, call

import src.server as server
from src.beds24.cache import CacheManager
from src.beds24.tools.calendar import BEDS24_OVERRIDES, PROPERTY_TIMEZONE

DATES = {"date_from": "2099-03-01", "date_to": "2099-03-03"}
ARGS = {**ROOM, **DATES}


def sent(beds24: Any) -> dict[str, Any]:
    [request] = beds24.requests
    assert request["method"] == "post"
    assert request["endpoint"] == "/inventory/rooms/calendar"
    [item] = request["body"]
    assert set(item) == {"roomId", "calendar"}
    assert item["roomId"] == ROOM["room_id"]
    [entry] = item["calendar"]
    return entry


@pytest.mark.parametrize(
    ("given", "fields"),
    [
        ({"min_stay": 3}, {"minStay": 3}),
        ({"max_stay": 7}, {"maxStay": 7}),
        ({"min_stay": 2, "max_stay": 2}, {"minStay": 2, "maxStay": 2}),
        ({"override": "none"}, {"override": "none"}),
        ({"min_stay": 1, "override": "blackout"}, {"minStay": 1, "override": "blackout"}),
    ],
)
async def test_sends_only_the_given_fields(mcp: Any, beds24: Any, given: dict[str, Any], fields: dict[str, Any]) -> None:
    result = await call(mcp, "set_stay_restrictions", {**ARGS, **given})
    assert result["success"] is True
    assert sent(beds24) == {"from": "2099-03-01", "to": "2099-03-03", **fields}


@pytest.mark.parametrize(("name", "value"), BEDS24_OVERRIDES.items())
async def test_override_names_map_to_beds24(mcp: Any, beds24: Any, name: str, value: str) -> None:
    await call(mcp, "set_stay_restrictions", {**ARGS, "override": name})
    assert sent(beds24)["override"] == value


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({}, "at least one of"),
        ({"min_stay": 0}, "min_stay must be"),
        ({"min_stay": 366}, "min_stay must be"),
        ({"max_stay": 0}, "max_stay must be"),
        ({"max_stay": 365}, "max_stay must be"),
        ({"min_stay": 4, "max_stay": 3}, "not be more than"),
        ({"min_stay": 2, "date_from": "2099-03-04"}, "not be after"),
        ({"min_stay": 2, "date_from": "2020-01-01"}, "in the past"),
        ({"min_stay": 2, "date_from": "01/03/2099"}, "date_from must be a date"),
        ({"min_stay": 2, "date_to": "20990303"}, "date_to must be a date"),
        ({"min_stay": 2, "date_to": "2099-02-30"}, "date_to must be a date"),
    ],
)
async def test_bad_input_is_rejected_without_calling_beds24(
    mcp: Any, beds24: Any, args: dict[str, Any], error: str
) -> None:
    result = await call(mcp, "set_stay_restrictions", {**ARGS, **args})
    assert result["success"] is False
    assert error in result["error"]
    assert beds24.requests == []


async def test_unknown_override_is_rejected(mcp: Any, beds24: Any) -> None:
    result = await mcp.call_tool("set_stay_restrictions", {**ARGS, "override": "noCheckIn"}, raise_on_error=False)
    assert result.is_error
    assert beds24.requests == []


async def test_today_in_melbourne_is_allowed_and_yesterday_is_not(mcp: Any, beds24: Any) -> None:
    today = datetime.now(PROPERTY_TIMEZONE).date()
    for day, ok in ((today, True), (today - timedelta(days=1), False)):
        args = {**ARGS, "date_from": day.isoformat(), "min_stay": 2}
        assert (await call(mcp, "set_stay_restrictions", args))["success"] is ok


async def test_returns_the_modified_entries(mcp: Any, beds24: Any) -> None:
    modified = {"roomId": 560912, "calendar": [{"from": "2099-03-01", "to": "2099-03-03", "minStay": 3}]}
    beds24.post_reply = [{"success": True, "modified": modified}]
    result = await call(mcp, "set_stay_restrictions", {**ARGS, "min_stay": 3})
    assert result["data"]["modified"] == modified
    assert result["data"]["sent"] == {"minStay": 3}


@pytest.mark.parametrize(
    "reply",
    [
        [{"success": True, "errors": [{"message": "bad"}]}],
        [{"success": True, "warnings": [{"message": "ignored"}]}],
        [{"success": False}],
        [],
        {"success": True},
    ],
)
async def test_errors_and_warnings_are_not_success(mcp: Any, beds24: Any, reply: Any) -> None:
    beds24.post_reply = reply
    result = await call(mcp, "set_stay_restrictions", {**ARGS, "min_stay": 3})
    assert result["success"] is False


async def test_write_clears_the_cached_calendar(mcp: Any, beds24: Any) -> None:
    server.resources.cache_manager = CacheManager()
    read = {**ARGS}
    await call(mcp, "get_calendar", read)
    assert (await call(mcp, "get_calendar", read))["metadata"]["source"] == "cache"
    await call(mcp, "set_stay_restrictions", {**ARGS, "min_stay": 3})
    assert (await call(mcp, "get_calendar", read))["metadata"]["source"] == "api"


async def test_get_calendar_asks_for_stay_limits_and_overrides(mcp: Any, beds24: Any) -> None:
    await call(mcp, "get_calendar", ARGS)
    params = beds24.requests[0]["params"]
    for name in ("includeMinStay", "includeMaxStay", "includeOverride", "includeNumAvail", "includePrices"):
        assert params[name] == "true"
