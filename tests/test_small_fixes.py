"""Cached availability shape, review cap, and rate-limit detection."""

from typing import Any

import httpx
import pytest
from conftest import call

import src.beds24.client as client_module
import src.server as server
from src.beds24.cache import CacheManager
from src.beds24.client import Beds24Client, is_rate_limited
from src.beds24.tools.reviews import REVIEW_LIMIT
from src.exceptions import Beds24Error

# --- check_availability returns the same shape from the cache as from Beds24 -----------------------


async def test_check_availability_cache_hit_matches_miss(mcp: Any, beds24: Any) -> None:
    cache = CacheManager()
    if not cache._enabled:
        pytest.skip("caching disabled in this environment")
    server.resources.cache_manager = cache
    args = {"property_id": 1, "check_in": "2027-03-01", "check_out": "2027-03-03"}
    beds24.get_reply = {"success": True, "data": [{"roomId": 1, "offers": [{"offerId": 1, "price": 100}]}]}

    miss = await call(mcp, "check_availability", args)
    hit = await call(mcp, "check_availability", args)

    assert len(beds24.requests) == 1
    assert miss["metadata"]["cache"] == "miss"
    assert hit["metadata"]["cache"] == "hit"
    assert hit["data"] == miss["data"]
    assert hit["data"]["available"] is True
    assert hit["metadata"]["truncated"] is False


# --- get_reviews says when Beds24's 100-review cap may have cut results off ------------------------


@pytest.mark.parametrize(
    ("reply", "truncated"),
    [
        ({"success": True, "data": [{"id": n} for n in range(REVIEW_LIMIT)]}, True),
        ({"success": True, "data": [{"id": 1}], "pages": {"nextPageExists": True}}, True),
        ({"success": True, "data": [{"id": 1}], "pages": {"nextPageExists": False}}, False),
        ({"success": True, "data": []}, False),
    ],
)
async def test_reviews_report_truncation(mcp: Any, beds24: Any, reply: dict[str, Any], truncated: bool) -> None:
    beds24.get_reply = reply
    result = await call(mcp, "get_reviews", {"channel": "airbnb", "room_id": 1})
    assert result["metadata"]["truncated"] is truncated
    assert len(beds24.requests) == 1


# --- rate limits are recognised by code, not by any "1016" in the text ----------------------------


@pytest.mark.parametrize(
    ("status", "code", "msg", "expected"),
    [
        (429, None, "Too many requests", True),
        (400, 1016, "anything", True),
        (400, "1020", "anything", True),
        (400, None, "Error 1016: credit limit exceeded", True),
        (400, None, "Booking 101600 not found", False),
        (400, None, "Room 1016 does not exist", False),
        (400, 400, "Invalid bookingId 1016", False),
        (500, None, "", False),
    ],
)
def test_is_rate_limited(status: int, code: Any, msg: str, expected: bool) -> None:
    assert is_rate_limited(status, code, msg) is expected


class ReplyingHttp:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.calls = 0

    async def request(self, **kwargs: Any) -> httpx.Response:
        self.calls += 1
        return self.response


class FakeAuth:
    async def get_access_token(self) -> str:
        return "token"


async def attempts(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> tuple[int, type]:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", no_sleep)
    client = Beds24Client(FakeAuth())  # type: ignore[arg-type]
    http = ReplyingHttp(response)

    async def get_http() -> ReplyingHttp:
        return http

    monkeypatch.setattr(client, "_get_http_client", get_http)
    with pytest.raises(Beds24Error) as error:
        await client._make_request("GET", "/bookings")
    return http.calls, type(error.value)


async def test_error_mentioning_1016_is_not_retried_as_a_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    response = httpx.Response(400, json={"success": False, "code": 400, "error": "Invalid bookingId 1016"})
    calls, error = await attempts(monkeypatch, response)
    assert calls == 1
    assert error is client_module.Beds24APIError


async def test_429_is_retried_then_reported_as_a_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    response = httpx.Response(429, json={"success": False, "code": 429, "error": "Too many requests"})
    calls, error = await attempts(monkeypatch, response)
    assert calls == 1 + Beds24Client.MAX_RETRIES
    assert error is client_module.Beds24RateLimitError
