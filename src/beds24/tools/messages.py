"""
Beds24 Message Tools
~~~~~~~~~~~~~~~~~~~~

5 MCP tools for message management:
1. get_messages - Get messages for a booking
2. get_unread_messages - Get all unread messages
3. send_message - Send message to guest
4. add_internal_note - Add internal note to booking
5. mark_messages_read - Mark messages as read

NOTE: Messages are NOT cached (real-time, time-sensitive data)
"""

from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from src.beds24.client import confirmed_post_item, get_all_pages
from src.logger import get_logger

logger = get_logger(__name__)

READ_ONLY = {"readOnlyHint": True, "openWorldHint": True}


def _post_item_confirmed(item: Any) -> bool:
    """True if one result of a Beds24 POST reports success with no errors."""
    return isinstance(item, dict) and item.get("success") is True and not item.get("errors")


def register_message_tools(mcp: FastMCP) -> None:
    """Register all message tools with FastMCP."""

    @mcp.tool(annotations=READ_ONLY)
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
            date_from: Only return messages from roughly this date onward (YYYY-MM-DD).
                Beds24 filters by whole days back from today: at least the last day,
                at most 999 days.

        Returns:
            List of message objects with booking, sender, and content information.
            metadata.truncated is True if more pages existed than were read.
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
                query_params["maxAge"] = min(max((datetime.now().date() - from_date).days, 1), 999)

            # Get messages from API (not cached - real-time required)
            response = await get_all_pages(client, "/bookings/messages", query_params)

            if not response or not response.get("success"):
                return {
                    "success": False,
                    "error": response.get("error") if response else "Failed to retrieve messages",
                }

            messages = response.get("data", [])

            return {
                "success": True,
                "data": messages,
                "metadata": {
                    "count": len(messages),
                    "cached": False,
                    "truncated": response["truncated"],
                },
            }

        except Exception as e:
            logger.error(f"Error in get_messages: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to get messages: {str(e)}",
            }

    @mcp.tool(annotations=READ_ONLY)
    async def get_unread_messages() -> dict[str, Any]:
        """
        Get all unread messages.

        Retrieves all unread messages across all bookings. Messages are
        NOT cached to ensure real-time data.

        Returns:
            List of unread message objects. metadata.truncated is True if more
            pages existed than were read.
        """
        from src.server import get_resources

        try:
            resources = get_resources()
            client = resources.beds24_client

            # Query for unread messages only
            query_params = {"filter": "unread"}

            response = await get_all_pages(client, "/bookings/messages", query_params)

            if not response or not response.get("success"):
                return {
                    "success": False,
                    "error": response.get("error") if response else "Failed to retrieve unread messages",
                }

            messages = response.get("data", [])

            return {
                "success": True,
                "data": messages,
                "metadata": {
                    "count": len(messages),
                    "cached": False,
                    "truncated": response["truncated"],
                },
            }

        except Exception as e:
            logger.error(f"Error in get_unread_messages: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to get unread messages: {str(e)}",
            }

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
    async def send_message(
        booking_id: int,
        message: str,
    ) -> dict[str, Any]:
        """
        Send message to guest for a booking.

        Sends a message to the guest associated with a booking. The message
        will be recorded in Beds24's messaging system.

        Args:
            booking_id: The booking ID to send message to
            message: The message text content

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

            # Send message via POST /bookings/messages
            response = await client.post("/bookings/messages", [message_data])

            if confirmed_post_item(response) is None:
                return {
                    "success": False,
                    "error": f"Beds24 did not confirm the message was sent: {response}",
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

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
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

            if confirmed_post_item(response) is None:
                return {
                    "success": False,
                    "error": f"Beds24 did not confirm the note was added: {response}",
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

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
    async def mark_messages_read(message_ids: list[int]) -> dict[str, Any]:
        """
        Mark messages as read.

        Sets each message to read in Beds24. Does not delete or change message
        content, and marking an already-read message again is harmless. Succeeds
        only if Beds24 confirms every message; otherwise lists the ids that failed.

        Args:
            message_ids: Beds24 message IDs (the "id" of each message from
                get_messages / get_unread_messages), at least one

        Returns:
            The ids marked read, or the ids that failed
        """
        from src.server import get_resources

        try:
            if not message_ids:
                return {"success": False, "error": "message_ids must contain at least one message ID"}

            client = get_resources().beds24_client

            logger.info("mark_messages_read called", extra={"count": len(message_ids)})

            response = await client.post(
                "/bookings/messages",
                [{"id": message_id, "read": True} for message_id in message_ids],
            )

            results = response if isinstance(response, list) else []
            failed = [
                message_id
                for index, message_id in enumerate(message_ids)
                if index >= len(results) or not _post_item_confirmed(results[index])
            ]
            if failed:
                return {
                    "success": False,
                    "error": f"Beds24 did not confirm these messages were marked read: {failed}",
                    "data": {"failed_ids": failed},
                }

            return {
                "success": True,
                "data": {"message_ids": message_ids},
                "metadata": {"marked_read": len(message_ids)},
            }

        except Exception as e:
            logger.error(f"Error in mark_messages_read: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to mark messages read: {str(e)}",
            }

    logger.info("Registered 5 message tools")
