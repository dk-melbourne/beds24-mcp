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
