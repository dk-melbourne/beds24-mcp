"""
Beds24 Property Tools
~~~~~~~~~~~~~~~~~~~~~

2 MCP tools for property management:
1. get_properties - List all properties
2. get_property_rooms - Get rooms for a specific property
"""

from typing import Any

from fastmcp import FastMCP

from src.exceptions import Beds24Error, ConfigurationError
from src.logger import get_logger
from src.schemas import GetPropertyRoomsParams, ToolResponse

logger = get_logger(__name__)


def register_property_tools(mcp: FastMCP) -> None:
    """Register all property tools with FastMCP."""

    @mcp.tool()
    async def get_properties() -> dict[str, Any]:
        """
        Get list of all properties.

        Retrieves all properties from Beds24 and caches the results
        for 24 hours.

        Returns:
            List of property objects with ID, name, and details
        """
        from src.server import get_resources

        try:
            resources = get_resources()
            client = resources.beds24_client
            cache = resources.cache_manager

            # Check cache for properties list
            cached_properties = cache.get_properties_list()

            if cached_properties is not None:
                logger.info("Properties retrieved from cache")
                return {
                    "success": True,
                    "data": cached_properties,
                    "metadata": {"cached": True, "count": len(cached_properties)},
                }

            # Cache miss - fetch from API
            response = await client.get("/properties")

            if not response or not response.get("success"):
                error_msg = response.get("error") if response else "Unknown error"
                logger.error(f"Failed to get properties: {error_msg}")
                return {
                    "success": False,
                    "error": f"Failed to get properties: {error_msg}",
                }

            properties = response.get("data", [])

            # Cache results (24h TTL)
            cache.cache_properties_list(properties)

            return {
                "success": True,
                "data": properties,
                "metadata": {"cached": False, "count": len(properties)},
            }

        except Exception as e:
            logger.error(f"Error in get_properties: {e}", exc_info=True)
            # Sanitize error message - only expose safe exception types
            if isinstance(e, (Beds24Error, ConfigurationError)):
                error_msg = str(e)
            else:
                error_msg = "An unexpected error occurred. Please contact support."
            return {
                "success": False,
                "error": error_msg,
            }

    @mcp.tool()
    async def get_property_rooms(property_id: int) -> dict[str, Any]:
        """
        Get rooms for a specific property.

        Retrieves all rooms for a given property ID and caches
        the results for 24 hours.

        Args:
            property_id: The property ID to get rooms for

        Returns:
            List of room objects for the property
        """
        from src.server import get_resources

        try:
            resources = get_resources()
            client = resources.beds24_client
            cache = resources.cache_manager

            # Check cache
            cached_rooms = cache.get_property_rooms(property_id)
            if cached_rooms is not None:
                logger.info(
                    "Property rooms retrieved from cache",
                    extra={"property_id": property_id},
                )
                return {
                    "success": True,
                    "data": cached_rooms,
                    "metadata": {"cached": True, "count": len(cached_rooms)},
                }

            # Cache miss - fetch from API
            response = await client.get(
                "/properties", {"id": property_id, "includeAllRooms": "true"}
            )

            if not response or not response.get("success"):
                error_msg = response.get("error") if response else "Unknown error"
                logger.error(
                    f"Failed to get property rooms: {error_msg}",
                    extra={"property_id": property_id},
                )
                return {
                    "success": False,
                    "error": f"Failed to get property rooms: {error_msg}",
                }

            properties = response.get("data", [])
            rooms = properties[0].get("roomTypes", []) if properties else []

            # Cache results (24h TTL)
            cache.cache_property_rooms(property_id, rooms)

            return {
                "success": True,
                "data": rooms,
                "metadata": {"cached": False, "count": len(rooms)},
            }

        except Exception as e:
            logger.error(
                f"Error in get_property_rooms: {e}",
                extra={"property_id": property_id},
                exc_info=True,
            )
            # Sanitize error message - only expose safe exception types
            if isinstance(e, (Beds24Error, ConfigurationError)):
                error_msg = str(e)
            else:
                error_msg = "An unexpected error occurred. Please contact support."
            return {
                "success": False,
                "error": error_msg,
            }

    logger.info("Registered 2 property tools")
