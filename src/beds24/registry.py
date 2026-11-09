"""
Beds24 Tool Registration
~~~~~~~~~~~~~~~~~~~~~~~~

Registers all 18 Beds24 MCP tools with the FastMCP server.

Tools organized by domain:
- Bookings: 6 tools (get, list, arrivals, departures, create, search)
- Properties: 2 tools (list, rooms)
- Availability: 2 tools (check, best price)
- Messages: 5 tools (list, unread, send, add note, mark read)
- Calendar: 4 tools (get, update pricing, set availability, block dates)

Total: 18 tools across 5 modules
"""

from typing import TYPE_CHECKING, Any

from src.logger import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)


def register_beds24_tools(mcp: "FastMCP", resources: Any) -> None:
    """
    Register all 18 Beds24 tools with the FastMCP server.

    Calls register functions from each tool module. Each module's register
    function creates @mcp.tool() decorated functions that have access to:
    - resources.beds24_client: Beds24 API client with rate limiting
    - resources.cache_manager: Multi-tier cache system
    - resources.auth_manager: OAuth token management

    Registration pattern:
    - Each tool module has a register_XXX_tools(mcp) function
    - Functions call get_resources() at runtime to access shared resources
    - All tools return dict[str, Any] with success/error and data fields

    Args:
        mcp: FastMCP server instance
        resources: Server resources (auth, client, cache, db)

    Raises:
        ImportError: If tool modules cannot be imported
        Exception: If registration fails for any tool module
    """
    logger.info("Registering Beds24 tools...")

    tool_count = 0

    # Register Bookings tools (6 tools)
    try:
        from src.beds24.tools.bookings import register_booking_tools

        register_booking_tools(mcp)
        tool_count += 6
        logger.info("Registered 6 booking tools")
    except ImportError as e:
        logger.error(f"Failed to import booking tools: {e}")
        raise
    except Exception as e:
        logger.error(f"Error registering booking tools: {e}")
        raise

    # Register Property tools (2 tools)
    try:
        from src.beds24.tools.properties import register_property_tools

        register_property_tools(mcp)
        tool_count += 2
        logger.info("Registered 2 property tools")
    except ImportError as e:
        logger.error(f"Failed to import property tools: {e}")
        raise
    except Exception as e:
        logger.error(f"Error registering property tools: {e}")
        raise

    # Register Availability tools (2 tools)
    try:
        from src.beds24.tools.availability import register_availability_tools

        register_availability_tools(mcp)
        tool_count += 2
        logger.info("Registered 2 availability tools")
    except ImportError as e:
        logger.error(f"Failed to import availability tools: {e}")
        raise
    except Exception as e:
        logger.error(f"Error registering availability tools: {e}")
        raise

    # Register Message tools (5 tools)
    try:
        from src.beds24.tools.messages import register_message_tools

        register_message_tools(mcp)
        tool_count += 5
        logger.info("Registered 5 message tools")
    except ImportError as e:
        logger.error(f"Failed to import message tools: {e}")
        raise
    except Exception as e:
        logger.error(f"Error registering message tools: {e}")
        raise

    # Register Calendar tools (4 tools)
    try:
        from src.beds24.tools.calendar import register_calendar_tools

        register_calendar_tools(mcp)
        tool_count += 4
        logger.info("Registered 4 calendar tools")
    except ImportError as e:
        logger.error(f"Failed to import calendar tools: {e}")
        raise
    except Exception as e:
        logger.error(f"Error registering calendar tools: {e}")
        raise

    # Register Review tools (1 tool)
    try:
        from src.beds24.tools.reviews import register_review_tools

        register_review_tools(mcp)
        tool_count += 1
        logger.info("Registered 1 review tool")
    except ImportError as e:
        logger.error(f"Failed to import review tools: {e}")
        raise
    except Exception as e:
        logger.error(f"Error registering review tools: {e}")
        raise

    # Register Invoice tools (1 tool)
    try:
        from src.beds24.tools.invoices import register_invoice_tools

        register_invoice_tools(mcp)
        tool_count += 1
        logger.info("Registered 1 invoice tool")
    except ImportError as e:
        logger.error(f"Failed to import invoice tools: {e}")
        raise
    except Exception as e:
        logger.error(f"Error registering invoice tools: {e}")
        raise

    logger.info(f"Successfully registered all {tool_count} Beds24 tools")
