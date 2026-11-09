"""
Beds24 Invoice Tools
~~~~~~~~~~~~~~~~~~~~

1 MCP tool:
1. get_invoices - Invoices for a booking

NOTE: Invoices are NOT cached.
"""

from typing import Any

from fastmcp import FastMCP

from src.beds24.client import get_all_pages
from src.logger import get_logger

logger = get_logger(__name__)


def register_invoice_tools(mcp: FastMCP) -> None:
    """Register invoice tools with FastMCP."""

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    async def get_invoices(booking_id: int) -> dict[str, Any]:
        """
        Get the invoices for a booking.

        Beds24 marks this endpoint Alpha, so behaviour may change. Use this to
        fetch invoices by booking ID alone. The booking tools (get_booking,
        get_bookings, ...) already ask Beds24 to include invoice items with each
        booking, so use those when you also need the booking's other details.

        Args:
            booking_id: The booking ID

        Returns:
            List of invoice objects (invoiceId, invoiceDate, invoiceItems).
            metadata.truncated is True if more pages existed than were read.
        """
        from src.server import get_resources

        try:
            client = get_resources().beds24_client
            response = await get_all_pages(client, "/bookings/invoices", {"bookingId": booking_id})

            if not response or not response.get("success"):
                return {
                    "success": False,
                    "error": response.get("error") if response else "Failed to retrieve invoices",
                }

            invoices = response.get("data", [])
            return {
                "success": True,
                "data": invoices,
                "metadata": {
                    "count": len(invoices),
                    "cached": False,
                    "truncated": response["truncated"],
                },
            }

        except Exception as e:
            logger.error(f"Error in get_invoices: {e}", exc_info=True)
            return {"success": False, "error": f"Failed to get invoices: {str(e)}"}

    logger.info("Registered 1 invoice tool")
