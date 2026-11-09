"""
Beds24 Calendar Tools
~~~~~~~~~~~~~~~~~~~~~

4 MCP tools for calendar management:
1. get_calendar - Get calendar data for property/room
2. update_pricing - Update room pricing for date range
3. set_availability - Set room availability for date range
4. block_dates - Block dates for a room
"""

from typing import Any

from fastmcp import FastMCP

from src.beds24.client import get_all_pages
from src.logger import get_logger

logger = get_logger(__name__)


def register_calendar_tools(mcp: FastMCP) -> None:
    """Register all calendar tools with FastMCP."""

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    async def get_calendar(
        property_id: int,
        date_from: str,
        date_to: str,
        room_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Get calendar data for property/room.

        Retrieves calendar data including pricing and availability for a date range.
        Results are cached for 15 minutes. If metadata.truncated is true, the range
        had more pages than were read; ask for a shorter date range.

        Args:
            property_id: The property ID to get calendar for
            date_from: Start date in YYYY-MM-DD format
            date_to: Last date in YYYY-MM-DD format (inclusive)
            room_id: Specific room ID (optional, gets all rooms if not specified)

        Returns:
            Calendar data with pricing and availability information
        """
        from src.server import get_resources
        from datetime import datetime

        try:
            resources = get_resources()
            client = resources.beds24_client
            cache = resources.cache_manager

            # Parse dates
            date_from_parsed = datetime.strptime(date_from, "%Y-%m-%d").date()
            date_to_parsed = datetime.strptime(date_to, "%Y-%m-%d").date()

            # Generate cache key from parameters
            query_params = {
                "property_id": property_id,
                "room_id": room_id,
                "date_from": date_from,
                "date_to": date_to,
            }
            cache_key = cache.make_query_key("calendar", query_params)

            # Check cache for existing data (15 minute TTL)
            cached_data = cache.get_calendar(cache_key)
            if cached_data is not None:
                logger.info(
                    "Calendar data retrieved from cache",
                    extra={
                        "property_id": property_id,
                        "room_id": room_id,
                    },
                )
                return {
                    "success": True,
                    "data": cached_data,
                    "metadata": {
                        "source": "cache",
                        "cache_key": cache_key,
                        "truncated": False,
                    },
                }

            # Cache miss - fetch from API
            endpoint_params = {
                "propertyId": property_id,
                "startDate": date_from,
                "endDate": date_to,
                "includeNumAvail": "true",
                "includeMinStay": "true",
                "includePrices": "true",
            }

            if room_id:
                endpoint_params["roomId"] = room_id

            response_data = await get_all_pages(client, "/inventory/rooms/calendar", endpoint_params)

            # Cache the result, but never a partial one
            if not response_data["truncated"]:
                cache.cache_calendar(cache_key, response_data)

            logger.info(
                "Calendar data retrieved from API",
                extra={
                    "property_id": property_id,
                    "room_id": room_id,
                    "date_from": date_from,
                    "date_to": date_to,
                },
            )

            return {
                "success": True,
                "data": response_data,
                "metadata": {
                    "source": "api",
                    "cache_key": cache_key,
                    "truncated": response_data["truncated"],
                },
            }

        except Exception as e:
            logger.error(
                f"Failed to get calendar: {e}",
                extra={
                    "property_id": property_id,
                    "room_id": room_id,
                },
                exc_info=True,
            )
            return {
                "success": False,
                "error": f"Failed to get calendar: {str(e)}",
                "metadata": {"error_type": type(e).__name__},
            }

    async def _write_calendar(
        action: str,
        room_id: int,
        date_from: str,
        date_to: str,
        values: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """POST one date range to /inventory/rooms/calendar and check Beds24's reply."""
        from src.server import get_resources

        try:
            resources = get_resources()
            body = [{"roomId": room_id, "calendar": [{"from": date_from, "to": date_to, **values}]}]
            response_data = await resources.beds24_client.post("/inventory/rooms/calendar", body)
            resources.cache_manager.invalidate_calendar()

            item = response_data[0] if isinstance(response_data, list) and response_data else {}
            if not isinstance(item, dict) or item.get("success") is not True or item.get("errors"):
                logger.error(f"Beds24 rejected {action}", extra={"room_id": room_id})
                return {
                    "success": False,
                    "error": f"Beds24 did not confirm the change: {response_data}",
                    "metadata": {"error_type": "Beds24Rejected"},
                }

            logger.info(f"{action} succeeded", extra={"room_id": room_id, "date_from": date_from, "date_to": date_to})
            return {
                "success": True,
                "data": {**result, "room_id": room_id, "date_from": date_from, "date_to": date_to, "api_response": item},
                "metadata": {"cache_invalidated": True},
            }

        except Exception as e:
            logger.error(f"Failed to {action}: {e}", extra={"room_id": room_id}, exc_info=True)
            return {
                "success": False,
                "error": f"Failed to {action}: {str(e)}",
                "metadata": {"error_type": type(e).__name__},
            }

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True}
    )
    async def update_pricing(
        property_id: int,
        room_id: int,
        date_from: str,
        date_to: str,
        price: float,
    ) -> dict[str, Any]:
        """
        Update room pricing for date range.

        Sets the calendar price (price1) for a room on every night from date_from
        to date_to, inclusive. Reports success only if Beds24 confirms the change.
        Prices are managed by PriceLabs, which will overwrite a manual price on its
        next sync, so only use this when the user explicitly asks for it.

        Args:
            property_id: The property ID containing the room
            room_id: The room ID to update pricing for
            date_from: First night in YYYY-MM-DD format
            date_to: Last night in YYYY-MM-DD format (inclusive)
            price: The new price per night

        Returns:
            Confirmation with update details
        """
        return await _write_calendar(
            "update pricing", room_id, date_from, date_to,
            {"price1": price}, {"property_id": property_id, "price": price},
        )

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True}
    )
    async def set_availability(
        property_id: int,
        room_id: int,
        date_from: str,
        date_to: str,
        available: int,
    ) -> dict[str, Any]:
        """
        Set room availability for date range.

        Sets the number of available units for a room on every night from
        date_from to date_to, inclusive. Reports success only if Beds24 confirms.

        Args:
            property_id: The property ID containing the room
            room_id: The room ID to update
            date_from: First night in YYYY-MM-DD format
            date_to: Last night in YYYY-MM-DD format (inclusive)
            available: Number of available units to set

        Returns:
            Confirmation with update details
        """
        return await _write_calendar(
            "set availability", room_id, date_from, date_to,
            {"numAvail": available}, {"property_id": property_id, "available": available},
        )

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True}
    )
    async def block_dates(
        property_id: int,
        room_id: int,
        date_from: str,
        date_to: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Block dates for a room (set availability to 0).

        Sets availability to 0 for every night from date_from to date_to,
        inclusive. Reports success only if Beds24 confirms.

        Args:
            property_id: The property ID containing the room
            room_id: The room ID to block dates for
            date_from: First night in YYYY-MM-DD format
            date_to: Last night in YYYY-MM-DD format (inclusive)
            reason: Optional reason, returned in the result only (not saved in Beds24)

        Returns:
            Confirmation with blocking details
        """
        return await _write_calendar(
            "block dates", room_id, date_from, date_to,
            {"numAvail": 0}, {"property_id": property_id, "blocked": True, "reason": reason},
        )

    logger.info("Registered 4 calendar tools")
