"""
Beds24 Authentication Manager
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

OAuth 2.0 token lifecycle management for Beds24 API v2.

Authentication Flow:
1. Initial Setup (one-time):
   - Use invite code to obtain refresh token
   - Store refresh token securely in environment

2. Regular Operations:
   - Use refresh token to get access token
   - Access token expires after ~1 hour
   - Automatic refresh when <1 minute remaining

Token Storage:
- Refresh token: Long-lived, stored in environment
- Access token: Short-lived, cached in memory with expiry tracking

Thread Safety:
- Uses asyncio.Lock to prevent concurrent refresh attempts
- Multiple requests can safely call get_access_token()
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx

from src.config import settings
from src.exceptions import Beds24AuthenticationError
from src.logger import get_logger

logger = get_logger(__name__)


class TokenDetails:
    """OAuth token details with expiry tracking."""

    def __init__(self, token: str, expires_at: datetime, refresh_token: str):
        self.token = token
        self.expires_at = expires_at
        self.refresh_token = refresh_token


class Beds24AuthManager:
    """
    Manages OAuth 2.0 authentication for Beds24 API.

    CRITICAL FEATURES:
    - Automatic token refresh when <1 minute remaining
    - Refresh token rotation handling
    - Thread-safe token access via asyncio.Lock
    - Network retry logic for token refresh
    """

    BASE_URL = "https://beds24.com/api/v2"

    def __init__(self, refresh_token: str | None = None) -> None:
        """
        Initialize authentication manager.

        Args:
            refresh_token: OAuth refresh token from initial setup
                          Defaults to settings.beds24_refresh_token
        """
        self.refresh_token = refresh_token or settings.beds24_refresh_token
        self.token_details: TokenDetails | None = None
        self._refresh_lock = asyncio.Lock()
        self._http_client: httpx.AsyncClient | None = None
        logger.info("Initialized Beds24 authentication manager")

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        logger.info("Closed authentication manager")

    async def get_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.

        CRITICAL: Call this before EVERY API request!

        Returns cached token if valid for >1 minute, otherwise refreshes.

        Returns:
            Valid access token string

        Raises:
            Beds24AuthenticationError: If no refresh token or refresh fails
        """
        # Check if cached token is still valid (>1 minute remaining)
        if (
            self.token_details
            and self.token_details.expires_at > datetime.now() + timedelta(seconds=60)
        ):
            return self.token_details.token

        # Refresh token (with lock to prevent concurrent refreshes)
        async with self._refresh_lock:
            # Double-check after acquiring lock (another request may have refreshed)
            if (
                self.token_details
                and self.token_details.expires_at
                > datetime.now() + timedelta(seconds=60)
            ):
                return self.token_details.token

            return await self._refresh_access_token()

    async def _refresh_access_token(self) -> str:
        """
        Exchange refresh token for new access token.

        CRITICAL: Updates both access token AND refresh token!

        Returns:
            New access token

        Raises:
            Beds24AuthenticationError: If refresh fails
        """
        if not self.refresh_token:
            raise Beds24AuthenticationError(
                "No refresh token available. Run setup_with_invite_code() first."
            )

        client = await self._get_http_client()

        try:
            # Exchange refresh token for access token
            response = await client.get(
                f"{self.BASE_URL}/authentication/token",
                headers={"refreshToken": self.refresh_token},
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Token refresh failed: {error_text}")
                raise Beds24AuthenticationError(f"Failed to refresh token: {error_text}")

            data = response.json()

            # Validate response
            if "token" not in data or "expiresIn" not in data:
                raise Beds24AuthenticationError(
                    f"Invalid token response: missing required fields"
                )

            # Update cached token
            self.token_details = TokenDetails(
                token=data["token"],
                expires_at=datetime.now() + timedelta(seconds=data["expiresIn"]),
                refresh_token=data.get("refreshToken", self.refresh_token),
            )

            # CRITICAL: Update refresh token (it may rotate)
            old_refresh_token = self.refresh_token
            self.refresh_token = data.get("refreshToken", self.refresh_token)

            if self.refresh_token != old_refresh_token:
                logger.warning(
                    "Refresh token rotated! Update environment variable BEDS24_REFRESH_TOKEN"
                )
                # TODO: Automatically update .env file if possible

            logger.info(
                f"Access token refreshed successfully (expires in {data['expiresIn']}s)"
            )
            return data["token"]

        except httpx.HTTPError as e:
            logger.error(f"Network error during token refresh: {e}")
            raise Beds24AuthenticationError(f"Network error: {str(e)}") from e

    async def setup_with_invite_code(
        self, invite_code: str, device_name: str | None = None
    ) -> str:
        """
        Initial setup: Exchange invite code for refresh token (one-time).

        ONE-TIME OPERATION - Run this once, then store refresh token.

        Args:
            invite_code: One-time invite code from Beds24 settings
            device_name: Optional device identifier

        Returns:
            Refresh token (SAVE THIS in environment!)

        Raises:
            Beds24AuthenticationError: If setup fails
        """
        client = await self._get_http_client()

        headers: dict[str, str] = {"code": invite_code}
        if device_name:
            headers["deviceName"] = device_name

        try:
            response = await client.get(
                f"{self.BASE_URL}/authentication/setup", headers=headers
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Setup failed: {error_text}")
                raise Beds24AuthenticationError(f"Failed to setup: {error_text}")

            data = response.json()

            # Validate response
            if "token" not in data or "refreshToken" not in data:
                raise Beds24AuthenticationError(
                    "Invalid setup response: missing required fields"
                )

            # Store tokens
            self.refresh_token = data["refreshToken"]
            self.token_details = TokenDetails(
                token=data["token"],
                expires_at=datetime.now() + timedelta(seconds=data["expiresIn"]),
                refresh_token=data["refreshToken"],
            )

            logger.info("Authentication setup completed successfully")
            logger.warning(
                "SAVE THIS REFRESH TOKEN in .env file: "
                f"BEDS24_REFRESH_TOKEN={data['refreshToken']}"
            )

            return data["refreshToken"]

        except httpx.HTTPError as e:
            logger.error(f"Network error during setup: {e}")
            raise Beds24AuthenticationError(f"Network error: {str(e)}") from e

    async def revoke_token(self) -> None:
        """
        Revoke the current access token.

        This invalidates the token but does NOT invalidate the refresh token.

        Raises:
            Beds24AuthenticationError: If no active token or revoke fails
        """
        if not self.token_details:
            raise Beds24AuthenticationError("No active token to revoke")

        client = await self._get_http_client()

        try:
            response = await client.delete(
                f"{self.BASE_URL}/authentication/token",
                headers={"token": self.token_details.token},
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Token revocation failed: {error_text}")
                raise Beds24AuthenticationError(f"Failed to revoke token: {error_text}")

            # Clear cached token (keep refresh token)
            self.token_details = None
            logger.info("Access token revoked successfully")

        except httpx.HTTPError as e:
            logger.error(f"Network error during revocation: {e}")
            raise Beds24AuthenticationError(f"Network error: {str(e)}") from e

    async def get_token_details(self) -> dict[str, Any]:
        """
        Get token details and diagnostics from Beds24.

        Returns:
            Token metadata including permissions, usage, etc.

        Raises:
            Beds24AuthenticationError: If request fails
        """
        token = await self.get_access_token()
        client = await self._get_http_client()

        try:
            response = await client.get(
                f"{self.BASE_URL}/authentication/details", headers={"token": token}
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Failed to get token details: {error_text}")
                raise Beds24AuthenticationError(
                    f"Failed to get token details: {error_text}"
                )

            return response.json()

        except httpx.HTTPError as e:
            logger.error(f"Network error getting token details: {e}")
            raise Beds24AuthenticationError(f"Network error: {str(e)}") from e

    def has_refresh_token(self) -> bool:
        """Check if we have a refresh token."""
        return self.refresh_token is not None

    def has_valid_access_token(self) -> bool:
        """Check if we have a valid (not expired) access token."""
        return (
            self.token_details is not None
            and self.token_details.expires_at > datetime.now()
        )

    def is_token_valid(self) -> bool:
        """
        Check if current access token is valid.

        Returns:
            True if token exists and not expired
        """
        return self.has_valid_access_token()

    def clear_token(self) -> None:
        """Clear cached access token (force refresh on next request)."""
        self.token_details = None
        logger.info("Cleared cached access token")

    def get_refresh_token(self) -> str | None:
        """Get the current refresh token."""
        return self.refresh_token

    def set_refresh_token(self, refresh_token: str) -> None:
        """
        Set the refresh token (useful for loading from config).

        Args:
            refresh_token: OAuth refresh token
        """
        self.refresh_token = refresh_token
        self.token_details = None  # Force refresh on next getAccessToken call
        logger.info("Refresh token updated")
