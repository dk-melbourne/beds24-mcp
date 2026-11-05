"""
FastMCP Server Implementation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Production-ready MCP server with complete lifecycle management, middleware,
and transport support for Beds24 integration.

Architecture:
- Uses FastMCP framework for MCP protocol implementation
- Supports stdio (Claude Desktop) and HTTP/SSE (remote) transports
- Automatic tool registration from beds24/ module
- Comprehensive middleware pipeline
- Graceful shutdown with resource cleanup

Critical Components:
- Beds24 API client with sequential rate limiting
- Multi-tier caching system
- OAuth token management
- Request/response logging
"""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastmcp import FastMCP

from src.beds24.auth import Beds24AuthManager
from src.beds24.cache import CacheManager
from src.beds24.client import Beds24Client
from src.config import settings
from src.logger import get_logger, setup_logging
from src.exceptions import (
    ConfigurationError,
    DKMCPError,
    Beds24Error,
)

# Initialize logging
setup_logging()
logger = get_logger(__name__)


class ServerResources:
    """Global server resources container."""

    def __init__(self) -> None:
        """Initialize resource container."""
        # Beds24 components
        self.auth_manager: Beds24AuthManager | None = None
        self.beds24_client: Beds24Client | None = None
        self.cache_manager: CacheManager | None = None

        # Server state
        self.initialized = False
        self.shutdown_event: asyncio.Event | None = None

    async def initialize(self) -> None:
        """Initialize all server resources."""
        if self.initialized:
            logger.warning("Resources already initialized")
            return

        logger.info("Initializing server resources...")

        try:
            # Initialize shutdown event
            self.shutdown_event = asyncio.Event()

            # Initialize cache manager
            logger.info("Initializing cache manager...")
            self.cache_manager = CacheManager()

            # Initialize Beds24 authentication
            logger.info("Initializing Beds24 authentication...")
            if not settings.beds24_refresh_token:
                logger.warning(
                    "BEDS24_REFRESH_TOKEN not configured. "
                    "Beds24 tools will require authentication setup."
                )
                self.auth_manager = Beds24AuthManager()
            else:
                self.auth_manager = Beds24AuthManager(settings.beds24_refresh_token)

            # Initialize Beds24 API client with sequential rate limiter
            logger.info("Initializing Beds24 API client with rate limiter...")
            self.beds24_client = Beds24Client(self.auth_manager)

            self.initialized = True
            logger.info("Server resources initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize server resources: {e}")
            await self.cleanup()
            raise ConfigurationError(f"Resource initialization failed: {str(e)}") from e

    async def cleanup(self) -> None:
        """Cleanup all server resources."""
        logger.info("Cleaning up server resources...")

        # Close Beds24 client
        if self.beds24_client:
            try:
                await self.beds24_client.close()
                logger.info("Beds24 client closed")
            except Exception as e:
                logger.error(f"Error closing Beds24 client: {e}")

        # Close auth manager
        if self.auth_manager:
            try:
                await self.auth_manager.close()
                logger.info("Auth manager closed")
            except Exception as e:
                logger.error(f"Error closing auth manager: {e}")

        # Clear caches
        if self.cache_manager:
            try:
                self.cache_manager.clear_all()
                logger.info("Caches cleared")
            except Exception as e:
                logger.error(f"Error clearing caches: {e}")

        self.initialized = False
        logger.info("Server resources cleaned up")


# Global resources instance
resources = ServerResources()


# ============================================================================
# FastMCP Lifespan Manager
# ============================================================================


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncGenerator[None, None]:
    """
    FastMCP lifespan manager for startup and shutdown.

    Args:
        server: FastMCP server instance

    Yields:
        None during server lifetime
    """
    logger.info("Starting FastMCP server...")

    try:
        # Initialize all resources
        await resources.initialize()

        logger.info("FastMCP server started successfully")

        yield  # Server is running

    finally:
        # Cleanup on shutdown
        logger.info("Shutting down FastMCP server...")
        await resources.cleanup()
        logger.info("FastMCP server shutdown complete")


# ============================================================================
# Server Creation
# ============================================================================


def create_server() -> FastMCP:
    """
    Create and configure the FastMCP server with middleware and tool registration.

    Returns:
        Configured FastMCP server instance
    """
    logger.info("Creating FastMCP server instance...")

    # Create server with lifespan manager for proper resource initialization
    mcp = FastMCP(
        name="beds24",
        version="1.0.0",
        instructions="Beds24 MCP Server",
        lifespan=lifespan,  # This ensures resources.initialize() runs on startup
    )

    # Register tools (import here to avoid circular dependencies)
    logger.info("Registering MCP tools...")
    register_tools(mcp)

    logger.info("FastMCP server created successfully")
    return mcp


def register_tools(mcp: FastMCP) -> None:
    """
    Auto-discover and register all MCP tools.

    Discovers tools from:
    - src/beds24/tools/*.py (Beds24 tools)

    Args:
        mcp: FastMCP server instance
    """
    try:
        # Register Beds24 tools (18 tools)
        from src.beds24.registry import register_beds24_tools

        register_beds24_tools(mcp, resources)
        logger.info("Registered Beds24 tools")

    except ImportError as e:
        logger.warning(f"Failed to import Beds24 tools: {e}")
    except Exception as e:
        logger.error(f"Error registering Beds24 tools: {e}")


# ============================================================================
# Middleware (Request/Response Interceptors)
# ============================================================================


class ServerMiddleware:
    """
    Middleware pipeline for request/response processing.

    Handles:
    - Request logging
    - Error handling and conversion to MCP format
    - Performance monitoring
    - Rate limit enforcement
    """

    @staticmethod
    async def log_request(tool_name: str, args: dict[str, Any]) -> None:
        """
        Log incoming tool request.

        Args:
            tool_name: Name of the MCP tool
            args: Tool arguments
        """
        if settings.log_requests:
            # Sanitize args (remove sensitive data)
            safe_args = {k: v for k, v in args.items() if k not in ["token", "password"]}
            logger.info(f"Tool request: {tool_name} args={safe_args}")

    @staticmethod
    async def log_response(tool_name: str, success: bool, duration_ms: float) -> None:
        """
        Log tool response.

        Args:
            tool_name: Name of the MCP tool
            success: Whether the request succeeded
            duration_ms: Request duration in milliseconds
        """
        if settings.log_requests:
            status = "success" if success else "error"
            logger.info(f"Tool response: {tool_name} status={status} duration={duration_ms:.2f}ms")

    @staticmethod
    def convert_exception_to_mcp_error(e: Exception) -> dict[str, Any]:
        """
        Convert Python exception to MCP error format.

        Args:
            e: Exception to convert

        Returns:
            MCP error response dict
        """
        error_type = type(e).__name__

        # Map custom exceptions to user-friendly messages
        if isinstance(e, Beds24Error):
            return {
                "error": str(e),
                "type": error_type,
                "category": "Beds24API",
                "retryable": isinstance(e, Beds24Error) and not isinstance(e, ConfigurationError),
            }
        elif isinstance(e, ConfigurationError):
            return {
                "error": str(e),
                "type": error_type,
                "category": "Configuration",
                "retryable": False,
            }
        else:
            # Generic error
            return {
                "error": f"An unexpected error occurred: {str(e)}",
                "type": error_type,
                "category": "Internal",
                "retryable": False,
            }


# ============================================================================
# Signal Handlers for Graceful Shutdown
# ============================================================================


def setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown."""

    def signal_handler(signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name}, initiating graceful shutdown...")

        # Set shutdown event
        if resources.shutdown_event:
            resources.shutdown_event.set()

        # Run cleanup in event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(resources.cleanup())
        else:
            loop.run_until_complete(resources.cleanup())

        sys.exit(0)

    # Register handlers
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # kill


# ============================================================================
# Main Entry Point
# ============================================================================


def main() -> None:
    """Main entry point for server startup."""
    logger.info("=" * 60)
    logger.info("Beds24 MCP Server")
    logger.info(f"Transport: {settings.mcp_transport}")
    logger.info(f"Log Level: {settings.log_level}")
    logger.info("=" * 60)

    # Setup signal handlers
    setup_signal_handlers()

    # Create server
    server = create_server()

    # Run server with appropriate transport
    if settings.mcp_transport == "stdio":
        logger.info("Starting server with stdio transport (Claude Desktop)")
        # FastMCP handles stdio automatically
        server.run()

    elif settings.mcp_transport == "http":
        logger.info(f"Starting server with HTTP/SSE transport on port {settings.mcp_server_port}")

        # HTTP/SSE transport requires uvicorn
        try:
            import uvicorn

            uvicorn.run(
                server,
                host="0.0.0.0",
                port=settings.mcp_server_port,
                log_level=settings.log_level.lower(),
            )

        except ImportError:
            logger.error("HTTP transport requires uvicorn. Install with: pip install uvicorn")
            sys.exit(1)

    else:
        logger.error(f"Invalid transport: {settings.mcp_transport}")
        sys.exit(1)


# ============================================================================
# Server Instance Access
# ============================================================================


# Global server instance (created on demand)
_mcp_server: FastMCP | None = None


def get_server() -> FastMCP:
    """
    Get or create the global MCP server instance.

    Returns:
        FastMCP server instance
    """
    global _mcp_server

    if _mcp_server is None:
        _mcp_server = create_server()

    return _mcp_server


def get_resources() -> ServerResources:
    """
    Get the global server resources.

    Returns:
        ServerResources instance
    """
    return resources


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    main()
