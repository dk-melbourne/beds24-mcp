"""
Configuration Management
~~~~~~~~~~~~~~~~~~~~~~~~

Centralized configuration loading from environment variables with validation.
Uses pydantic-settings for type-safe configuration management.
"""

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ========================================================================
    # Beds24 API Configuration
    # ========================================================================

    beds24_refresh_token: str = Field(
        default="",
        description="Beds24 OAuth refresh token for API authentication",
    )

    beds24_invite_code: str | None = Field(
        default=None,
        description="One-time invite code for initial setup",
    )

    beds24_api_base_url: str = Field(
        default="https://beds24.com/api/v2",
        description="Beds24 API base URL",
    )

    # ========================================================================
    # MCP Transport Configuration
    # ========================================================================

    mcp_transport: Literal["stdio", "http"] = Field(
        default="stdio",
        description="MCP transport mode",
    )

    mcp_server_port: int = Field(
        default=3000,
        description="HTTP server port (when using HTTP transport)",
    )

    mcp_api_key: str | None = Field(
        default=None,
        description="API key for HTTP transport authentication",
    )

    mcp_allowed_origins: str = Field(
        default="*",
        description="CORS allowed origins (comma-separated)",
    )

    mcp_request_timeout: int = Field(
        default=30,
        description="Request timeout in seconds",
    )

    # ========================================================================
    # Rate Limiting Configuration
    # ========================================================================

    beds24_rate_limit_concurrent: int = Field(
        default=1,
        description="Maximum concurrent Beds24 API requests (DO NOT CHANGE)",
    )

    beds24_rate_limit_delay: float = Field(
        default=2.5,
        description="Delay between Beds24 API requests in seconds",
    )

    beds24_max_retries: int = Field(
        default=3,
        description="Maximum retry attempts for failed requests",
    )

    beds24_retry_backoff: float = Field(
        default=2.0,
        description="Exponential backoff multiplier for retries",
    )

    # ========================================================================
    # Caching Configuration
    # ========================================================================

    cache_enabled: bool = Field(
        default=True,
        description="Enable/disable caching",
    )

    cache_ttl_properties: int = Field(
        default=86400,
        description="Properties cache TTL in seconds (24 hours)",
    )

    cache_ttl_bookings: int = Field(
        default=300,
        description="Bookings cache TTL in seconds (5 minutes)",
    )

    cache_ttl_availability: int = Field(
        default=600,
        description="Availability cache TTL in seconds (10 minutes)",
    )

    cache_ttl_calendar: int = Field(
        default=900,
        description="Calendar cache TTL in seconds (15 minutes)",
    )

    cache_ttl_messages: int = Field(
        default=0,
        description="Messages cache TTL in seconds (0 = no cache)",
    )

    cache_max_size: int = Field(
        default=1000,
        description="Maximum number of cached items",
    )

    # ========================================================================
    # Logging Configuration
    # ========================================================================

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )

    log_format: Literal["json", "text"] = Field(
        default="json",
        description="Log output format",
    )

    log_requests: bool = Field(
        default=False,
        description="Enable request/response logging",
    )

    log_file: str | None = Field(
        default=None,
        description="Log file path (None = stdout only)",
    )

    # ========================================================================
    # Development Settings
    # ========================================================================

    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )

    dev_mode: bool = Field(
        default=False,
        description="Enable development features",
    )

    @field_validator("beds24_rate_limit_concurrent")
    @classmethod
    def validate_concurrent_limit(cls, v: int) -> int:
        """Validate that concurrent request limit is 1 (Beds24 requirement)."""
        if v != 1:
            raise ValueError(
                "Beds24 API only allows 1 concurrent request. "
                "DO NOT modify BEDS24_RATE_LIMIT_CONCURRENT."
            )
        return v

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.mcp_allowed_origins.split(",")]


# Global settings instance
settings = Settings()
