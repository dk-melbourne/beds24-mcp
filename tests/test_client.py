"""Client helpers that don't need a tool to test."""

from typing import Any

from conftest import FakeBeds24Client

from src.beds24.client import get_all_pages


def page(rows: list[Any], more: bool) -> dict[str, Any]:
    return {"success": True, "data": rows, "pages": {"nextPageExists": more}}


async def test_get_all_pages_follows_next_page_until_the_end() -> None:
    fake = FakeBeds24Client()
    fake.get_replies = [page([1, 2], True), page([3], True), page([4], False)]
    result = await get_all_pages(fake, "/bookings", {"status": "confirmed"})
    assert result["data"] == [1, 2, 3, 4]
    assert result["count"] == 4
    assert result["truncated"] is False
    assert [r["params"] for r in fake.requests] == [
        {"status": "confirmed", "page": 1},
        {"status": "confirmed", "page": 2},
        {"status": "confirmed", "page": 3},
    ]


async def test_get_all_pages_stops_at_max_pages_and_says_so() -> None:
    fake = FakeBeds24Client()
    fake.get_replies = [page([n], True) for n in range(5)]
    result = await get_all_pages(fake, "/bookings", max_pages=2)
    assert result["data"] == [0, 1]
    assert result["truncated"] is True
    assert len(fake.requests) == 2


async def test_get_all_pages_handles_a_reply_without_pages_or_data() -> None:
    fake = FakeBeds24Client()
    fake.get_reply = {"success": True}
    result = await get_all_pages(fake, "/properties")
    assert result["data"] == []
    assert result["truncated"] is False


# --- get_all_pages never hides a failed page ---------------------------------------------------


async def test_get_all_pages_returns_a_failed_page_instead_of_partial_rows() -> None:
    fake = FakeBeds24Client()
    error = {"success": False, "error": "boom", "pages": {"nextPageExists": True}}
    fake.get_replies = [page([1], True), error, page([3], False)]
    result = await get_all_pages(fake, "/bookings")
    assert result == error
    assert len(fake.requests) == 2


async def test_get_all_pages_handles_non_dict_and_non_list_replies() -> None:
    fake = FakeBeds24Client()
    fake.get_reply = ["not", "a", "dict"]
    assert (await get_all_pages(fake, "/bookings"))["success"] is False
    fake.get_reply = {"success": True, "data": {"not": "a list"}}
    assert (await get_all_pages(fake, "/bookings"))["success"] is False


# --- writes are never retried once they may have reached Beds24 ----------------------------------

import httpx  # noqa: E402
import pytest  # noqa: E402

import src.beds24.client as client_module  # noqa: E402
from src.beds24.client import Beds24Client  # noqa: E402


class FailingHttp:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    async def request(self, **kwargs: Any) -> Any:
        self.calls += 1
        raise self.error


class FakeAuth:
    async def get_access_token(self) -> str:
        return "token"


async def attempts(monkeypatch: pytest.MonkeyPatch, method: str, error: Exception) -> int:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", no_sleep)
    client = Beds24Client(FakeAuth())  # type: ignore[arg-type]
    http = FailingHttp(error)

    async def get_http() -> FailingHttp:
        return http

    monkeypatch.setattr(client, "_get_http_client", get_http)
    with pytest.raises(client_module.Beds24APIError):
        await client._make_request(method, "/bookings/messages", json=[{"bookingId": 1}])
    return http.calls


READ_TIMEOUT = httpx.ReadTimeout("timed out")
CONNECT_ERROR = httpx.ConnectError("refused")


async def test_write_is_not_retried_after_it_may_have_reached_beds24(monkeypatch: pytest.MonkeyPatch) -> None:
    assert await attempts(monkeypatch, "POST", READ_TIMEOUT) == 1


async def test_write_is_retried_when_it_never_reached_beds24(monkeypatch: pytest.MonkeyPatch) -> None:
    assert await attempts(monkeypatch, "POST", CONNECT_ERROR) == 1 + Beds24Client.MAX_RETRIES


async def test_read_is_retried_after_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    assert await attempts(monkeypatch, "GET", READ_TIMEOUT) == 1 + Beds24Client.MAX_RETRIES
