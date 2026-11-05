"""
Application Entry Point
~~~~~~~~~~~~~~~~~~~~~~~

Main entry point for the Beds24 MCP server. Handles transport selection
and server initialization.

Usage:
    # stdio transport (default)
    python -m src.main

    # HTTP transport
    MCP_TRANSPORT=http python -m src.main
"""

import asyncio
import sys

from src.config import settings
from src.logger import get_logger, setup_logging
from src.server import get_server

# Initialize logging
setup_logging()
logger = get_logger(__name__)


def run_stdio() -> None:
    """Run server with stdio transport (default for Claude Desktop)."""
    logger.info("Starting MCP server with stdio transport")

    try:
        from src.server import get_resources

        mcp = get_server()

        # Initialize resources before running server
        # (lifespan manager might not trigger properly in stdio mode)
        logger.info("Initializing server resources...")
        asyncio.run(get_resources().initialize())

        # Run server with stdio transport
        mcp.run(transport="stdio")

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down")
    except Exception as e:
        logger.exception(f"Server error: {e}")
        sys.exit(1)
    finally:
        # TODO: Add shutdown lifecycle
        # await shutdown()
        logger.info("Server stopped")


async def run_http() -> None:
    """Run server with HTTP/SSE transport (for remote access)."""
    logger.info(
        f"Starting MCP server with HTTP transport on port {settings.mcp_server_port}"
    )

    try:
        from src.server import get_resources

        mcp = get_server()

        # Initialize resources before running server
        logger.info("Initializing server resources...")
        await get_resources().initialize()

        # Run server with HTTP transport
        await mcp.run_async(
            transport="http",
            port=settings.mcp_server_port,
            # TODO: Add authentication middleware
            # TODO: Add CORS configuration
        )

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down")
    except Exception as e:
        logger.exception(f"Server error: {e}")
        sys.exit(1)
    finally:
        # TODO: Add shutdown lifecycle
        # await shutdown()
        logger.info("Server stopped")


def main() -> None:
    """Main entry point."""
    logger.info(f"Beds24 MCP Server v1.0.0")
    logger.info(f"Transport: {settings.mcp_transport}")
    logger.info(f"Log level: {settings.log_level}")
    logger.info(f"Debug mode: {settings.debug}")

    # Select transport based on configuration
    if settings.mcp_transport == "http":
        asyncio.run(run_http())
    else:
        run_stdio()  # Manages its own event loop


if __name__ == "__main__":
    main()
