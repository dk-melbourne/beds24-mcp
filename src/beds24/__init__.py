"""
Beds24 Integration Module
~~~~~~~~~~~~~~~~~~~~~~~~~~

Complete Beds24 API integration with 18 MCP tools for property management.

Components:
- auth: OAuth 2.0 token management
- client: Rate-limited API client (CRITICAL: 1 request at a time, 2.5s delay)
- cache: Multi-tier caching layer
- types: Pydantic models for all API responses
- registry: Tool registration with FastMCP
- tools/: 18 tool implementations across 5 modules

Critical Implementation Notes:
- Beds24 API allows ONLY 1 concurrent request
- Minimum 2.5 second delay between requests required
- Excessive requests trigger account-level blocking
- Sequential queue pattern is mandatory for all API calls
"""

__all__ = [
    "Beds24AuthManager",
    "Beds24Client",
    "CacheManager",
]

# TODO: Import after implementation
# from src.beds24.auth import Beds24AuthManager
# from src.beds24.client import Beds24Client
# from src.beds24.cache import CacheManager
