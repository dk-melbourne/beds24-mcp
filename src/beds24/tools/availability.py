"""
Beds24 Availability Tools
~~~~~~~~~~~~~~~~~~~~~~~~~

2 MCP tools for availability checking:
1. check_availability - Check room availability for dates
2. get_best_price - Get best available price for dates
"""

from datetime import date
from typing import Any

from fastmcp import FastMCP

from src.beds24.client import get_all_pages
from src.logger import get_logger

logger = get_logger(__name__)


def register_availability_tools(mcp: FastMCP) -> None:
    """Register all availability tools with FastMCP."""

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    async def check_availability(
        property_id: int,
        check_in: str,
        check_out: str,
        num_adults: int = 1,
        num_children: int = 0,
        room_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Check room availability for specific dates.

        Checks if rooms are available for the specified dates at a property.
        Results are cached for 10 minutes.

        Args:
            property_id: Property ID to check availability for
            check_in: Check-in date (YYYY-MM-DD format)
            check_out: Check-out date (YYYY-MM-DD format)
            num_adults: Number of adults (default 1)
            num_children: Number of children (default 0)
            room_id: Specific room ID to check (optional)

        Returns:
            Availability status with list of available rooms and pricing
        """
        from src.server import get_resources
        from datetime import datetime

        try:
            resources = get_resources()
            client = resources.beds24_client
            cache = resources.cache_manager

            # Parse dates
            check_in_date = datetime.strptime(check_in, "%Y-%m-%d").date()
            check_out_date = datetime.strptime(check_out, "%Y-%m-%d").date()

            # Generate cache key from params
            cache_key = cache.make_query_key("availability", {
                "property_id": property_id,
                "room_id": room_id,
                "check_in": check_in,
                "check_out": check_out,
                "num_adults": num_adults,
                "num_children": num_children,
            })

            # Check cache first (10min TTL)
            cached_result = cache.get_availability(cache_key)
            if cached_result is not None:
                logger.info(
                    "availability cache hit",
                    extra={
                        "property_id": property_id,
                        "cache_key": cache_key,
                    },
                )
                return {
                    "success": True,
                    "data": cached_result,
                    "metadata": {"cache": "hit", "ttl_seconds": 600},
                }

            # Build API parameters
            api_params: dict[str, Any] = {
                "propertyId": property_id,
                "arrival": check_in,
                "departure": check_out,
                "numAdults": num_adults,
                "numChildren": num_children,
            }

            if room_id:
                api_params["roomId"] = room_id

            # Call API: GET /inventory/rooms/offers
            api_response = await get_all_pages(client, "/inventory/rooms/offers", api_params)
            # A failed request is not "no availability": report it and cache nothing.
            if not api_response.get("success"):
                return {
                    "success": False,
                    "error": f"Beds24 returned an error: {api_response.get('error') or api_response}",
                }

            truncated = bool(isinstance(api_response, dict) and api_response.get("truncated"))

            # Extract available rooms from response
            available_rooms = []
            if isinstance(api_response, dict):
                rooms_data = api_response.get("data", [])
            else:
                rooms_data = api_response if isinstance(api_response, list) else []

            for room in rooms_data:
                if not isinstance(room, dict):
                    continue

                offers = room.get("offers", [])
                if offers:
                    available_rooms.append({
                        "room_id": room.get("roomId"),
                        "property_id": room.get("propertyId"),
                        "room_name": room.get("roomName"),
                        "offers": [
                            {
                                "offer_id": offer.get("offerId"),
                                "price": offer.get("price"),
                                "currency": offer.get("currency"),
                                "num_nights": offer.get("numNights"),
                                "min_stay": offer.get("minStay"),
                                "max_stay": offer.get("maxStay"),
                            }
                            for offer in offers
                        ],
                    })

            # Cache the results (10min TTL), but never a partial list
            if not truncated:
                cache.cache_availability(cache_key, available_rooms)

            logger.info(
                "check_availability succeeded",
                extra={
                    "property_id": property_id,
                    "num_rooms": len(available_rooms),
                },
            )

            return {
                "success": True,
                "data": {
                    "available": len(available_rooms) > 0,
                    "rooms": available_rooms,
                },
                "metadata": {"cache": "miss", "ttl_seconds": 600, "truncated": truncated},
            }

        except Exception as e:
            logger.error(
                "check_availability failed",
                extra={
                    "property_id": property_id,
                    "error": str(e),
                },
            )
            return {
                "success": False,
                "error": f"Failed to check availability: {str(e)}",
            }

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    async def get_best_price(
        property_id: int,
        check_in: str,
        check_out: str,
        num_adults: int = 1,
        num_children: int = 0,
    ) -> dict[str, Any]:
        """
        Get best available price for dates.

        Finds the lowest available price across all rooms for the specified dates.
        Results are cached for 10 minutes.

        Args:
            property_id: Property ID to check prices for
            check_in: Check-in date (YYYY-MM-DD format)
            check_out: Check-out date (YYYY-MM-DD format)
            num_adults: Number of adults (default 1)
            num_children: Number of children (default 0)

        Returns:
            Best price details with room and offer information
        """
        from src.server import get_resources
        from datetime import datetime

        try:
            resources = get_resources()
            client = resources.beds24_client
            cache = resources.cache_manager

            # Generate cache key from params
            cache_key = cache.make_query_key("best_price", {
                "property_id": property_id,
                "check_in": check_in,
                "check_out": check_out,
                "num_adults": num_adults,
                "num_children": num_children,
            })

            # Check cache first (10min TTL)
            cached_result = cache.get_availability(cache_key)
            if cached_result is not None:
                logger.info(
                    "best_price cache hit",
                    extra={
                        "property_id": property_id,
                        "cache_key": cache_key,
                    },
                )
                return {
                    "success": True,
                    "data": cached_result,
                    "metadata": {"cache": "hit", "ttl_seconds": 600},
                }

            # Build API parameters
            api_params: dict[str, Any] = {
                "propertyId": property_id,
                "arrival": check_in,
                "departure": check_out,
                "numAdults": num_adults,
                "numChildren": num_children,
            }

            # Call API: GET /inventory/rooms/offers
            api_response = await get_all_pages(client, "/inventory/rooms/offers", api_params)
            # A failed request is not "no availability": report it and cache nothing.
            if not api_response.get("success"):
                return {
                    "success": False,
                    "error": f"Beds24 returned an error: {api_response.get('error') or api_response}",
                }

            truncated = bool(isinstance(api_response, dict) and api_response.get("truncated"))

            # Extract rooms from response
            if isinstance(api_response, dict):
                rooms_data = api_response.get("data", [])
            else:
                rooms_data = api_response if isinstance(api_response, list) else []

            # Find the best (cheapest) price across all rooms
            best_price_info = None
            best_price = float("inf")

            for room in rooms_data:
                if not isinstance(room, dict):
                    continue

                offers = room.get("offers", [])
                for offer in offers:
                    if not isinstance(offer, dict):
                        continue

                    price = offer.get("price", float("inf"))
                    if price < best_price:
                        best_price = price
                        best_price_info = {
                            "room_id": room.get("roomId"),
                            "property_id": room.get("propertyId"),
                            "room_name": room.get("roomName"),
                            "price": price,
                            "currency": offer.get("currency"),
                            "offer_id": offer.get("offerId"),
                            "num_nights": offer.get("numNights"),
                            "min_stay": offer.get("minStay"),
                            "max_stay": offer.get("maxStay"),
                        }

            # Cache the result (10min TTL), but never one from a partial list
            if not truncated:
                cache.cache_availability(cache_key, best_price_info)

            if best_price_info:
                logger.info(
                    "get_best_price succeeded",
                    extra={
                        "property_id": property_id,
                        "best_price": best_price,
                    },
                )
                return {
                    "success": True,
                    "data": best_price_info,
                    "metadata": {"cache": "miss", "ttl_seconds": 600, "truncated": truncated},
                }
            else:
                logger.info(
                    "get_best_price no availability",
                    extra={"property_id": property_id},
                )
                return {
                    "success": True,
                    "data": None,
                    "metadata": {
                        "cache": "miss",
                        "ttl_seconds": 600,
                        "reason": "No availability for dates",
                        "truncated": truncated,
                    },
                }

        except Exception as e:
            logger.error(
                "get_best_price failed",
                extra={
                    "property_id": property_id,
                    "error": str(e),
                },
            )
            return {
                "success": False,
                "error": f"Failed to get best price: {str(e)}",
            }

    logger.info("Registered 2 availability tools")
