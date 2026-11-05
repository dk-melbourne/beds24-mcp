"""
Beds24 MCP Server - FastMCP Deployment
======================================

MCP server providing access to:
- 18 Beds24 tools (bookings, properties, availability, messages, calendar)

"""

from src.server import get_server

# Create and export the server instance
# FastMCP hosts detect this instance and deploy it
mcp = get_server()

if __name__ == "__main__":
    # Local testing
    from src.server import main
    main()
