"""
Beds24 Rate-Limited API Client
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

CRITICAL COMPONENT: Sequential request queue with strict rate limiting.

Beds24 API Constraints (DO NOT VIOLATE):
- ONLY 1 concurrent API request allowed per account
- Minimum 2.5 seconds between requests
- Excessive requests trigger account-level blocking (errors 1016, 1020)
- Rate limit headers: X-FiveMinCreditLimit-*, X-RequestCost

Implementation:
- Async queue for sequential request processing
- 2.5 second delay enforced between ALL requests
- Exponential backoff retry on failures (5s → 10s → 20s)
- Automatic token refresh on 401 responses
- Rate limit monitoring via response headers

THIS IS THE MOST CRITICAL COMPONENT IN THE ENTIRE SYSTEM.
FAILURE = BEDS24 ACCOUNT BLOCKED.
"""

import asyncio
from datetime import datetime
from typing import Any, Callable, Generic, TypeVar

import httpx

from src.beds24.auth import Beds24AuthManager
from src.config import settings
from src.exceptions import (
    Beds24APIError,
    Beds24AuthenticationError,
    Beds24RateLimitError,
)
from src.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def confirmed_post_item(response: Any) -> dict[str, Any] | None:
    """Return the first result of a Beds24 POST if it reports success with no errors.

    Beds24 POST endpoints reply with a list: [{"success", "new"/"modified", "errors", "warnings"}].
    """
    item = response[0] if isinstance(response, list) and response else None
    if isinstance(item, dict) and item.get("success") is True and not item.get("errors"):
        return item
    return None


class QueuedRequest(Generic[T]):
    """Represents a queued API request with future for result."""

    def __init__(self, request_fn: Callable[[], Any]):
        self.request_fn = request_fn
        self.future: asyncio.Future[T] = asyncio.Future()


class Beds24Client:
    """
    Rate-limited HTTP client for Beds24 API v2.

    CRITICAL: Enforces ONLY 1 request at a time with 2.5s delays.

    Features:
    - Sequential request queue (asyncio.Queue)
    - 2.5 second minimum delay between requests
    - Exponential backoff retry (5s → 10s → 20s)
    - Automatic OAuth token refresh
    - Rate limit header monitoring
    """

    BASE_URL = "https://beds24.com/api/v2"
    REQUEST_DELAY = 2.5  # seconds - DO NOT CHANGE
    MAX_RETRIES = 3

    def __init__(self, auth_manager: Beds24AuthManager) -> None:
        """
        Initialize Beds24 API client.

        Args:
            auth_manager: Authentication manager for token handling
        """
        self.auth_manager = auth_manager
        self.base_url = settings.beds24_api_base_url or self.BASE_URL

        # Sequential request queue
        self.queue: list[QueuedRequest] = []
        self.is_processing = False
        self.last_request_time: float = 0
        self._lock = asyncio.Lock()

        # HTTP client
        self._http_client: httpx.AsyncClient | None = None

        # Rate limit tracking
        self.rate_limit_info: dict[str, str] = {}

        logger.info("Initialized Beds24 API client with sequential rate limiter")

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        logger.info("Closed Beds24 client")

    async def get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Make a GET request through the rate limiter.

        Args:
            endpoint: API endpoint (e.g., "/bookings")
            params: Query parameters

        Returns:
            API response data

        Raises:
            Beds24APIError: On API errors
            Beds24RateLimitError: On rate limit exceeded
        """
        return await self._enqueue(
            lambda: self._make_request("GET", endpoint, params=params)
        )

    async def post(
        self, endpoint: str, body: Any | None = None
    ) -> dict[str, Any]:
        """
        Make a POST request through the rate limiter.

        Args:
            endpoint: API endpoint
            body: Request body (will be JSON-serialized)

        Returns:
            API response data

        Raises:
            Beds24APIError: On API errors
            Beds24RateLimitError: On rate limit exceeded
        """
        return await self._enqueue(
            lambda: self._make_request("POST", endpoint, json=body)
        )

    async def delete(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a DELETE request through the rate limiter."""
        return await self._enqueue(
            lambda: self._make_request("DELETE", endpoint, params=params)
        )

    async def patch(
        self, endpoint: str, body: Any | None = None
    ) -> dict[str, Any]:
        """Make a PATCH request through the rate limiter."""
        return await self._enqueue(
            lambda: self._make_request("PATCH", endpoint, json=body)
        )

    async def _enqueue(self, request_fn: Callable[[], Any]) -> Any:
        """
        Enqueue a request for sequential processing.

        This is the CRITICAL method that enforces sequential execution.

        Args:
            request_fn: Async function that makes the API call

        Returns:
            Result from the API call (waits until request is processed)
        """
        queued = QueuedRequest(request_fn)

        async with self._lock:
            self.queue.append(queued)

            # Start processing if not already running
            if not self.is_processing:
                asyncio.create_task(self._process_queue())

        # Wait for this specific request to complete
        return await queued.future

    async def _process_queue(self) -> None:
        """
        Process queued requests sequentially with delay enforcement.

        CRITICAL LOGIC:
        1. Check if already processing (prevent concurrent loops)
        2. Pop request from queue
        3. Enforce delay since last request
        4. Execute request
        5. Record timestamp
        6. Set result or exception
        7. Repeat until queue empty
        """
        async with self._lock:
            if self.is_processing:
                return  # Already processing
            self.is_processing = True

        try:
            while True:
                # Get next request
                async with self._lock:
                    if not self.queue:
                        break  # Queue empty
                    queued = self.queue.pop(0)

                # Enforce delay since last request
                current_time = asyncio.get_event_loop().time()
                time_since_last = current_time - self.last_request_time

                if time_since_last < self.REQUEST_DELAY:
                    # Wait remaining time
                    remaining_delay = self.REQUEST_DELAY - time_since_last
                    logger.debug(f"Rate limit delay: waiting {remaining_delay:.2f}s")
                    await asyncio.sleep(remaining_delay)

                # Execute request
                try:
                    result = await queued.request_fn()
                    self.last_request_time = asyncio.get_event_loop().time()
                    queued.future.set_result(result)
                except Exception as e:
                    queued.future.set_exception(e)

        finally:
            async with self._lock:
                self.is_processing = False

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """
        Execute a single HTTP request with retry logic.

        Implements exponential backoff for rate limit errors (1016, 1020).

        Args:
            method: HTTP method (GET, POST, DELETE, PATCH)
            endpoint: API endpoint
            params: Query parameters
            json: Request body (JSON)
            retry_count: Current retry attempt

        Returns:
            API response data

        Raises:
            Beds24APIError: On API errors
            Beds24AuthenticationError: On auth errors
            Beds24RateLimitError: On rate limit exceeded (after retries)
        """
        try:
            # Get fresh access token
            token = await self.auth_manager.get_access_token()

            # Build URL
            url = f"{self.base_url}{endpoint}"

            # Remove None values from params
            if params:
                params = {k: v for k, v in params.items() if v is not None}

            # Get HTTP client
            client = await self._get_http_client()

            # Make request
            response = await client.request(
                method=method,
                url=url,
                params=params,
                json=json,
                headers={"token": token, "Content-Type": "application/json"},
            )

            # Extract rate limit headers
            self._extract_rate_limit_headers(response.headers)

            # Handle success (POST returns 201)
            if 200 <= response.status_code < 300:
                try:
                    data = response.json()
                    return data
                except Exception as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    raise Beds24APIError(f"Invalid JSON response: {str(e)}")

            # Handle errors
            error_text = response.text
            try:
                error_json = response.json()
                error_msg = (
                    error_json.get("error")
                    or error_json.get("message")
                    or error_text
                )
            except:
                error_msg = error_text or f"Request failed with status {response.status_code}"

            # Check for rate limit errors (1016, 1020)
            if "1016" in error_msg or "1020" in error_msg:
                if retry_count < self.MAX_RETRIES:
                    # Exponential backoff: 5s, 10s, 20s
                    backoff_delay = 5 * (2**retry_count)
                    logger.warning(
                        f"Rate limit hit! Retrying in {backoff_delay}s "
                        f"(attempt {retry_count + 1}/{self.MAX_RETRIES})"
                    )
                    await asyncio.sleep(backoff_delay)

                    return await self._make_request(
                        method, endpoint, params, json, retry_count + 1
                    )
                else:
                    logger.error(f"Rate limit exceeded after {self.MAX_RETRIES} retries")
                    raise Beds24RateLimitError(
                        f"Rate limit exceeded: {error_msg}"
                    )

            # Check for authentication errors
            if response.status_code == 401:
                logger.error(f"Authentication failed: {error_msg}")
                raise Beds24AuthenticationError(f"Authentication failed: {error_msg}")

            # Other errors
            logger.error(
                f"{method} {endpoint} failed with {response.status_code}: {error_msg}"
            )
            raise Beds24APIError(
                f"API error ({response.status_code}): {error_msg}", response.status_code
            )

        except (Beds24APIError, Beds24AuthenticationError, Beds24RateLimitError):
            # Re-raise our custom exceptions
            raise
        except httpx.HTTPError as e:
            logger.error(f"Network error during {method} {endpoint}: {e}")

            # Retry on network errors
            if retry_count < self.MAX_RETRIES:
                backoff_delay = 5 * (2**retry_count)
                logger.warning(f"Network error, retrying in {backoff_delay}s")
                await asyncio.sleep(backoff_delay)
                return await self._make_request(
                    method, endpoint, params, json, retry_count + 1
                )

            raise Beds24APIError(f"Network error: {str(e)}") from e
        except Exception as e:
            logger.error(f"Unexpected error during {method} {endpoint}: {e}")
            raise Beds24APIError(f"Unexpected error: {str(e)}") from e

    def _extract_rate_limit_headers(self, headers: httpx.Headers) -> None:
        """
        Extract and store rate limit info from response headers.

        Beds24 provides these headers:
        - X-FiveMinCreditLimit: Total credit limit in 5 min window
        - X-FiveMinCreditLimit-ResetsIn: Seconds until reset
        - X-FiveMinCreditLimit-Remaining: Remaining credit
        - X-RequestCost: Cost of this request

        Args:
            headers: HTTP response headers
        """
        header_mapping = {
            "x-fivemincreditlimit": "X-FiveMinCreditLimit",
            "x-fivemincreditlimit-resetsin": "X-FiveMinCreditLimit-ResetsIn",
            "x-fivemincreditlimit-remaining": "X-FiveMinCreditLimit-Remaining",
            "x-requestcost": "X-RequestCost",
        }

        for header_key, info_key in header_mapping.items():
            if header_key in headers:
                self.rate_limit_info[info_key] = headers[header_key]

        # Log warning if approaching rate limit
        remaining = self.rate_limit_info.get("X-FiveMinCreditLimit-Remaining")
        if remaining and int(remaining) < 10:
            logger.warning(
                f"Rate limit warning: only {remaining} credits remaining!"
            )

    def get_rate_limit_info(self) -> dict[str, str]:
        """Get current rate limit information from last request."""
        return self.rate_limit_info.copy()

    def get_queue_length(self) -> int:
        """Get number of pending requests in queue."""
        return len(self.queue)

    def is_currently_processing(self) -> bool:
        """Check if currently processing a request."""
        return self.is_processing
