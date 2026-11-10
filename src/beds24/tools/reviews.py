"""
Beds24 Review Tools
~~~~~~~~~~~~~~~~~~~

1 MCP tool:
1. get_reviews - Guest reviews from Airbnb or Booking.com

NOTE: Reviews are NOT cached.
"""

import datetime
from typing import Any, Literal

from fastmcp import FastMCP

from src.logger import get_logger

logger = get_logger(__name__)

# Beds24 returns at most this many reviews per call, and these endpoints have no page parameter.
REVIEW_LIMIT = 100


def register_review_tools(mcp: FastMCP) -> None:
    """Register review tools with FastMCP."""

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    async def get_reviews(
        channel: Literal["airbnb", "booking"],
        room_id: int | None = None,
        property_id: int | None = None,
        from_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Get guest reviews from Airbnb or Booking.com.

        Beds24 marks the Airbnb endpoint Beta and the Booking.com endpoint Alpha,
        so behaviour may change. Beds24 returns at most 100 reviews per call and
        these endpoints cannot page, so metadata.truncated is true when more may
        exist. Review fields differ between the two channels and are returned as
        Beds24 sends them.

        Args:
            channel: "airbnb" or "booking"
            room_id: Beds24 room ID (required for airbnb, not used for booking)
            property_id: Beds24 property ID (required for booking, not used for airbnb)
            from_date: Only reviews made on or after this date, YYYY-MM-DD
                (required for booking, not used for airbnb)

        Returns:
            List of review objects as returned by Beds24
        """
        from src.server import get_resources

        try:
            if channel == "airbnb":
                if room_id is None:
                    return {"success": False, "error": "room_id is required for the airbnb channel"}
                if property_id is not None or from_date is not None:
                    return {
                        "success": False,
                        "error": "property_id and from_date apply only to the booking channel",
                    }
                params: dict[str, Any] = {"roomId": room_id}
            elif channel == "booking":
                if property_id is None or not from_date:
                    return {
                        "success": False,
                        "error": "property_id and from_date (YYYY-MM-DD) are required for the booking channel",
                    }
                if room_id is not None:
                    return {"success": False, "error": "room_id applies only to the airbnb channel"}
                try:
                    datetime.date.fromisoformat(from_date)
                except ValueError:
                    return {"success": False, "error": "from_date must be a date in YYYY-MM-DD format"}
                params = {"propertyId": property_id, "from": from_date}
            else:
                return {"success": False, "error": "channel must be 'airbnb' or 'booking'"}

            client = get_resources().beds24_client
            response = await client.get(f"/channels/{channel}/reviews", params)

            if not response or not response.get("success"):
                return {
                    "success": False,
                    "error": response.get("error") if response else "Failed to retrieve reviews",
                }

            reviews = response.get("data", [])
            more = (response.get("pages") or {}).get("nextPageExists") is True
            truncated = more or len(reviews) >= REVIEW_LIMIT
            return {
                "success": True,
                "data": reviews,
                "metadata": {
                    "count": len(reviews), "channel": channel, "cached": False, "truncated": truncated,
                },
            }

        except Exception as e:
            logger.error(f"Error in get_reviews: {e}", exc_info=True)
            return {"success": False, "error": f"Failed to get reviews: {str(e)}"}

    logger.info("Registered 1 review tool")
