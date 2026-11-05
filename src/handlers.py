"""
Handler Registry
~~~~~~~~~~~~~~~~

Central registry for all MCP tool handlers. This module coordinates between
the MCP server and the domain-specific tool implementations.

Architecture:
    FastMCP Server
        ↓
    Handler Registry (this module)
        ↓
    Domain Registries (beds24.registry)
        ↓
    Tool Implementations
"""

from typing import Any

from src.logger import get_logger

logger = get_logger(__name__)


class HandlerRegistry:
    """
    Central registry for all MCP tool handlers.

    This class manages registration of tools from different domains
    (Beds24) and provides a unified interface for the MCP server.
    """

    def __init__(self) -> None:
        """Initialize the handler registry."""
        self._handlers: dict[str, Any] = {}
        logger.info("Initialized handler registry")

    def register_handler(self, name: str, handler: Any) -> None:
        """
        Register a tool handler.

        Args:
            name: Tool name (e.g., "get_bookings")
            handler: Tool handler function

        Raises:
            ValueError: If a handler with this name already exists
        """
        if name in self._handlers:
            raise ValueError(f"Handler '{name}' is already registered")

        self._handlers[name] = handler
        logger.debug(f"Registered handler: {name}")

    def get_handler(self, name: str) -> Any:
        """
        Get a registered handler.

        Args:
            name: Tool name

        Returns:
            Handler function

        Raises:
            KeyError: If handler not found
        """
        if name not in self._handlers:
            raise KeyError(f"Handler '{name}' not found")

        return self._handlers[name]

    def list_handlers(self) -> list[str]:
        """
        List all registered handler names.

        Returns:
            List of handler names
        """
        return list(self._handlers.keys())

    @property
    def count(self) -> int:
        """Get the number of registered handlers."""
        return len(self._handlers)


# Global registry instance
registry = HandlerRegistry()


# TODO: Import and register domain-specific tools after implementation
# from src.beds24.registry import register_beds24_tools
#
# def initialize_handlers() -> None:
#     """Initialize all tool handlers."""
#     logger.info("Initializing tool handlers")
#     register_beds24_tools(registry)
#     logger.info(f"Registered {registry.count} tool handlers")
