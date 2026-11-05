"""
Custom Exception Hierarchy
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Domain-specific exceptions for structured error handling across the application.
All exceptions inherit from DKMCPError for consistent error handling.
"""


class DKMCPError(Exception):
    """Base exception for all MCP server errors."""

    def __init__(self, message: str, details: dict[str, any] | None = None) -> None:
        """
        Initialize exception with message and optional details.

        Args:
            message: Human-readable error message
            details: Additional context for debugging
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}


# ============================================================================
# Beds24 API Exceptions
# ============================================================================


class Beds24Error(DKMCPError):
    """Base exception for Beds24 API errors."""

    pass


class Beds24AuthenticationError(Beds24Error):
    """Authentication or authorization failed."""

    pass


class Beds24RateLimitError(Beds24Error):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
        details: dict[str, any] | None = None,
    ) -> None:
        """
        Initialize rate limit error.

        Args:
            message: Error message
            retry_after: Seconds to wait before retrying
            details: Additional context
        """
        super().__init__(message, details)
        self.retry_after = retry_after


class Beds24APIError(Beds24Error):
    """Beds24 API returned an error response."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: dict[str, any] | None = None,
        details: dict[str, any] | None = None,
    ) -> None:
        """
        Initialize API error.

        Args:
            message: Error message
            status_code: HTTP status code
            response_body: API response body
            details: Additional context
        """
        super().__init__(message, details)
        self.status_code = status_code
        self.response_body = response_body or {}


class Beds24ValidationError(Beds24Error):
    """Request validation failed."""

    pass


class Beds24ResourceNotFoundError(Beds24Error):
    """Requested resource not found."""

    pass


# ============================================================================
# Configuration Exceptions
# ============================================================================


class ConfigurationError(DKMCPError):
    """Configuration is invalid or missing."""

    pass


# ============================================================================
# Caching Exceptions
# ============================================================================


class CacheError(DKMCPError):
    """Cache operation failed."""

    pass


# ============================================================================
# Transport Exceptions
# ============================================================================


class TransportError(DKMCPError):
    """MCP transport error."""

    pass


class TransportTimeoutError(TransportError):
    """Request timeout."""

    pass
