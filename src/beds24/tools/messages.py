"""
Beds24 Message Tools
~~~~~~~~~~~~~~~~~~~~

4 MCP tools for message management:
1. get_messages - Get messages for a booking
2. get_unread_messages - Get all unread messages
3. send_message - Send message to guest
4. add_internal_note - Add internal note to booking

NOTE: Messages are NOT cached (real-time, time-sensitive data)
"""

from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from src.logger import get_logger

logger = get_logger(__name__)


def register_message_tools(mcp: FastMCP) -> None:
    """Register all message tools with FastMCP."""

    @mcp.tool()
    async def get_messages(
        booking_id: int | None = None,
        unread_only: bool = False,
        date_from: str | None = None,
    ) -> dict[str, Any]:
        """
        Get messages for a booking or all messages.

        Retrieves messages from Beds24. Messages are NOT cached as they are
        time-sensitive data that should always reflect current state.

        Args:
            booking_id: Filter by specific booking ID (optional)
            unread_only: Only return unread messages (default False)
            date_from: Only return messages from this date onward (YYYY-MM-DD format)

        Returns:
            List of message objects with booking, sender, and content information
        """
        from src.server import get_resources

        try:
            resources = get_resources()
            client = resources.beds24_client

            # Build query parameters
            query_params: dict[str, Any] = {}

            if booking_id:
                query_params["bookingId"] = booking_id

            if unread_only:
                query_params["filter"] = "unread"

            if date_from:
                from_date = datetime.fromisoformat(date_from.split("T")[0]).date()
                query_params["maxAge"] = max((datetime.now().date() - from_date).days, 0)

            # Get messages from API (not cached - real-time required)
            response = await client.get("/bookings/messages", query_params)

            if not response or not response.get("success"):
                return {
                    "success": False,
                    "error": response.get("error") if response else "Failed to retrieve messages",
                }

            messages = response.get("data", [])

            return {
                "success": True,
                "data": messages,
                "metadata": {"count": len(messages), "cached": False},
            }

        except Exception as e:
            logger.error(f"Error in get_messages: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to get messages: {str(e)}",
            }

    @mcp.tool()
    async def get_unread_messages() -> dict[str, Any]:
        """
        Get all unread messages.

        Retrieves all unread messages across all bookings. Messages are
        NOT cached to ensure real-time data.

        Returns:
            List of unread message objects
        """
        from src.server import get_resources

        try:
            resources = get_resources()
            client = resources.beds24_client

            # Query for unread messages only
            query_params = {"filter": "unread"}

            response = await client.get("/bookings/messages", query_params)

            if not response or not response.get("success"):
                return {
                    "success": False,
                    "error": response.get("error") if response else "Failed to retrieve unread messages",
                }

            messages = response.get("data", [])

            return {
                "success": True,
                "data": messages,
                "metadata": {"count": len(messages), "cached": False},
            }

        except Exception as e:
            logger.error(f"Error in get_unread_messages: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to get unread messages: {str(e)}",
            }

    @mcp.tool()
    async def send_message(
        booking_id: int,
        message: str,
        subject: str | None = None,
    ) -> dict[str, Any]:
        """
        Send message to guest for a booking.

        Sends a message to the guest associated with a booking. The message
        will be recorded in Beds24's messaging system.

        Args:
            booking_id: The booking ID to send message to
            message: The message text content
            subject: Optional subject line for the message

        Returns:
            Confirmation with booking ID and message sent
        """
        from src.server import get_resources

        try:
            resources = get_resources()
            client = resources.beds24_client

            logger.info(
                "send_message called",
                extra={"booking_id": booking_id},
            )

            # Build message payload
            message_data: dict[str, Any] = {
                "bookingId": booking_id,
                "message": message,
            }

            if subject:
                message_data["subject"] = subject

            # Send message via POST /bookings/messages
            response = await client.post("/bookings/messages", [message_data])

            if not response or not response.get("success"):
                return {
                    "success": False,
                    "error": response.get("error") if response else "Failed to send message",
                }

            logger.info(
                f"Message sent successfully to booking {booking_id}",
            )

            return {
                "success": True,
                "data": {"booking_id": booking_id, "message": message},
                "metadata": {"message_sent": True},
            }

        except Exception as e:
            logger.error(f"Error in send_message: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to send message: {str(e)}",
            }

    @mcp.tool()
    async def add_internal_note(
        booking_id: int,
        note: str,
    ) -> dict[str, Any]:
        """
        Add internal note to a booking.

        Adds an internal note to a booking that is only visible to staff,
        not to the guest. Internal notes are useful for tracking issues,
        special requests, or other private information.

        Args:
            booking_id: The booking ID to add note to
            note: The internal note text

        Returns:
            Confirmation with booking ID and note added
        """
        from src.server import get_resources

        try:
            resources = get_resources()
            client = resources.beds24_client
            cache = resources.cache_manager

            logger.info(
                "add_internal_note called",
                extra={"booking_id": booking_id},
            )

            # Build note payload (internal note is a message with source="internalNote")
            note_data: dict[str, Any] = {
                "bookingId": booking_id,
                "message": note,
                "source": "internalNote",
            }

            # Add note via POST /bookings/messages
            response = await client.post("/bookings/messages", [note_data])

            if not response or not response.get("success"):
                return {
                    "success": False,
                    "error": response.get("error") if response else "Failed to add internal note",
                }

            # Invalidate booking cache for this booking since it was modified
            cache.invalidate("bookings", f"booking:{booking_id}")

            logger.info(
                f"Internal note added successfully to booking {booking_id}",
            )

            return {
                "success": True,
                "data": {"booking_id": booking_id, "note": note},
                "metadata": {"note_added": True, "cache_invalidated": True},
            }

        except Exception as e:
            logger.error(f"Error in add_internal_note: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to add internal note: {str(e)}",
            }

    logger.info("Registered 4 message tools")
