"""
Beds24 Booking Tools
~~~~~~~~~~~~~~~~~~~~

6 MCP tools for booking management:
1. get_bookings - List bookings with date/property filters
2. get_booking - Get single booking by ID
3. get_arrivals - Get today's/upcoming arrivals
4. get_departures - Get today's/upcoming departures
5. create_booking - Create new booking
6. search_bookings - Search by guest name/email/reference

Pattern: FastMCP @mcp.tool() decorator registration with access to
resources.beds24_client and resources.cache_manager.

Caching:
- Bookings: 5-minute TTL
- Query results: 5-minute TTL
- Invalidate all on write operations

Type Safety:
- Uses Pydantic schemas for input/output validation
- Comprehensive error handling
- Matches TypeScript behavior exactly
"""

from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from src.logger import get_logger

logger = get_logger(__name__)


def register_booking_tools(mcp: FastMCP) -> None:
    """Register all booking tools with FastMCP."""

    @mcp.tool()
    async def get_bookings(
        arrival_from: str | None = None,
        arrival_to: str | None = None,
        departure_from: str | None = None,
        departure_to: str | None = None,
        property_id: int | None = None,
        room_id: int | None = None,
        status: str | None = None,
        search_string: str | None = None,
    ) -> dict[str, Any]:
        """
        Get list of bookings with optional filters.

        Supports filtering by dates, property, room, status, and search string.
        Results are cached for 5 minutes.

        Args:
            arrival_from: Filter by arrival date from (YYYY-MM-DD)
            arrival_to: Filter by arrival date to (YYYY-MM-DD)
            departure_from: Filter by departure date from (YYYY-MM-DD)
            departure_to: Filter by departure date to (YYYY-MM-DD)
            property_id: Filter by property ID
            room_id: Filter by room ID
            status: Filter by booking status (confirmed, new, cancelled, etc.)
            search_string: Search in guest name, email, reference

        Returns:
            List of bookings matching filters
        """
        from src.server import get_resources

        try:
            resources = get_resources()
            client = resources.beds24_client
            cache = resources.cache_manager

            # Build query parameters
            query_params: dict[str, Any] = {}

            if arrival_from:
                query_params["arrivalFrom"] = arrival_from
            if arrival_to:
                query_params["arrivalTo"] = arrival_to
            if departure_from:
                query_params["departureFrom"] = departure_from
            if departure_to:
                query_params["departureTo"] = departure_to
            if property_id:
                query_params["propertyId"] = property_id
            if room_id:
                query_params["roomId"] = room_id
            if status:
                query_params["status"] = status
            if search_string:
                query_params["searchString"] = search_string

            # Always include invoice and info items
            query_params["includeInvoiceItems"] = True
            query_params["includeInfoItems"] = True

            # Generate cache key from params
            cache_key = cache.make_query_key("bookings", query_params)

            # Check cache first
            cached = cache.get_bookings_query(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for bookings query: {cache_key}")
                return {
                    "success": True,
                    "data": cached,
                    "metadata": {"cached": True, "cache_key": cache_key},
                }

            # Make API request
            response = await client.get("/bookings", query_params)

            if not response.get("success"):
                error_msg = response.get("error") or response.get("message") or "Unknown error"
                logger.error(f"Failed to get bookings: {error_msg}")
                return {
                    "success": False,
                    "error": f"Failed to get bookings: {error_msg}",
                }

            bookings_data = response.get("data", [])

            # Cache the results
            cache.cache_bookings_query(cache_key, bookings_data)

            return {
                "success": True,
                "data": bookings_data,
                "metadata": {"cached": False, "cache_key": cache_key, "count": len(bookings_data)},
            }

        except Exception as e:
            logger.error(f"Error in get_bookings: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def get_booking(booking_id: int) -> dict[str, Any]:
        """
        Get single booking by ID.

        Results are cached for 5 minutes.

        Args:
            booking_id: Beds24 booking ID

        Returns:
            Booking details or null if not found
        """
        from src.server import get_resources

        try:
            resources = get_resources()
            client = resources.beds24_client
            cache = resources.cache_manager

            # Check cache first
            cached = cache.get_booking(booking_id)
            if cached is not None:
                logger.debug(f"Cache hit for booking {booking_id}")
                return {
                    "success": True,
                    "data": cached,
                    "metadata": {"cached": True},
                }

            # Make API request
            response = await client.get("/bookings", {"id": booking_id})

            if not response.get("success"):
                error_msg = response.get("error") or response.get("message") or "Unknown error"
                logger.error(f"Failed to get booking {booking_id}: {error_msg}")
                return {
                    "success": False,
                    "error": f"Failed to get booking: {error_msg}",
                }

            bookings = response.get("data", [])
            booking = bookings[0] if bookings else None

            if booking:
                # Cache the result
                cache.cache_booking(booking_id, booking)

            return {
                "success": True,
                "data": booking,
                "metadata": {"cached": False},
            }

        except Exception as e:
            logger.error(f"Error in get_booking: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def get_arrivals(
        arrival_from: str, arrival_to: str, property_id: int | None = None
    ) -> dict[str, Any]:
        """
        Get bookings with arrivals in a date range.

        Useful for checking today's or upcoming arrivals.

        Args:
            arrival_from: Start date for arrival range (YYYY-MM-DD) - REQUIRED
            arrival_to: End date for arrival range (YYYY-MM-DD) - REQUIRED
            property_id: Filter by specific property (optional)

        Returns:
            List of bookings with arrivals in the specified range
        """
        from src.server import get_resources

        try:
            # Validate dates are in correct format
            try:
                datetime.strptime(arrival_from, "%Y-%m-%d")
                datetime.strptime(arrival_to, "%Y-%m-%d")
            except ValueError as e:
                return {
                    "success": False,
                    "error": f"Invalid date format. Expected YYYY-MM-DD: {str(e)}",
                }

            # Validate date logic
            if arrival_from > arrival_to:
                return {
                    "success": False,
                    "error": "arrival_from must be before or equal to arrival_to",
                }

            resources = get_resources()
            client = resources.beds24_client
            cache = resources.cache_manager

            # Build query parameters
            query_params: dict[str, Any] = {
                "arrivalFrom": arrival_from,
                "arrivalTo": arrival_to,
                "includeInvoiceItems": True,
                "includeInfoItems": True,
            }

            if property_id:
                query_params["propertyId"] = property_id

            # Generate cache key
            cache_key = cache.make_query_key("arrivals", query_params)

            # Check cache
            cached = cache.get_bookings_query(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for arrivals query")
                return {
                    "success": True,
                    "data": cached,
                    "metadata": {"cached": True},
                }

            # Make API request
            response = await client.get("/bookings", query_params)

            if not response.get("success"):
                error_msg = response.get("error") or response.get("message") or "Unknown error"
                logger.error(f"Failed to get arrivals: {error_msg}")
                return {
                    "success": False,
                    "error": f"Failed to get arrivals: {error_msg}",
                }

            arrivals = response.get("data", [])

            # Cache results
            cache.cache_bookings_query(cache_key, arrivals)

            return {
                "success": True,
                "data": arrivals,
                "metadata": {"cached": False, "count": len(arrivals)},
            }

        except Exception as e:
            logger.error(f"Error in get_arrivals: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def get_departures(
        departure_from: str, departure_to: str, property_id: int | None = None
    ) -> dict[str, Any]:
        """
        Get bookings with departures in a date range.

        Useful for checking today's or upcoming departures.

        Args:
            departure_from: Start date for departure range (YYYY-MM-DD) - REQUIRED
            departure_to: End date for departure range (YYYY-MM-DD) - REQUIRED
            property_id: Filter by specific property (optional)

        Returns:
            List of bookings with departures in the specified range
        """
        from src.server import get_resources

        try:
            # Validate dates are in correct format
            try:
                datetime.strptime(departure_from, "%Y-%m-%d")
                datetime.strptime(departure_to, "%Y-%m-%d")
            except ValueError as e:
                return {
                    "success": False,
                    "error": f"Invalid date format. Expected YYYY-MM-DD: {str(e)}",
                }

            # Validate date logic
            if departure_from > departure_to:
                return {
                    "success": False,
                    "error": "departure_from must be before or equal to departure_to",
                }

            resources = get_resources()
            client = resources.beds24_client
            cache = resources.cache_manager

            # Build query parameters
            query_params: dict[str, Any] = {
                "departureFrom": departure_from,
                "departureTo": departure_to,
                "includeInvoiceItems": True,
                "includeInfoItems": True,
            }

            if property_id:
                query_params["propertyId"] = property_id

            # Generate cache key
            cache_key = cache.make_query_key("departures", query_params)

            # Check cache
            cached = cache.get_bookings_query(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for departures query")
                return {
                    "success": True,
                    "data": cached,
                    "metadata": {"cached": True},
                }

            # Make API request
            response = await client.get("/bookings", query_params)

            if not response.get("success"):
                error_msg = response.get("error") or response.get("message") or "Unknown error"
                logger.error(f"Failed to get departures: {error_msg}")
                return {
                    "success": False,
                    "error": f"Failed to get departures: {error_msg}",
                }

            departures = response.get("data", [])

            # Cache results
            cache.cache_bookings_query(cache_key, departures)

            return {
                "success": True,
                "data": departures,
                "metadata": {"cached": False, "count": len(departures)},
            }

        except Exception as e:
            logger.error(f"Error in get_departures: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def create_booking(
        property_id: int,
        room_id: int,
        status: str,
        arrival: str,
        departure: str,
        num_adult: int,
        first_name: str,
        last_name: str,
        email: str,
        num_child: int | None = None,
        title: str | None = None,
        mobile: str | None = None,
        phone: str | None = None,
        address: str | None = None,
        city: str | None = None,
        state: str | None = None,
        postcode: str | None = None,
        country: str | None = None,
        channel: str | None = None,
        api_reference: str | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new booking.

        IMPORTANT: This operation invalidates all booking caches.

        Args:
            property_id: Property ID - REQUIRED
            room_id: Room ID - REQUIRED
            status: Booking status (confirmed, new, etc.) - REQUIRED
            arrival: Check-in date (YYYY-MM-DD) - REQUIRED
            departure: Check-out date (YYYY-MM-DD) - REQUIRED
            num_adult: Number of adults - REQUIRED
            first_name: Guest first name - REQUIRED
            last_name: Guest last name - REQUIRED
            email: Guest email - REQUIRED
            num_child: Number of children (optional)
            title: Guest title (optional)
            mobile: Guest mobile number (optional)
            phone: Guest phone number (optional)
            address: Guest address (optional)
            city: Guest city (optional)
            state: Guest state/province (optional)
            postcode: Guest postal code (optional)
            country: Guest country (optional)
            channel: Booking channel (Direct, Airbnb, etc.) (optional)
            api_reference: External reference/confirmation code (optional)
            comment: Booking notes (optional)

        Returns:
            Created booking details
        """
        from src.server import get_resources

        try:
            # Validate required dates
            try:
                datetime.strptime(arrival, "%Y-%m-%d")
                datetime.strptime(departure, "%Y-%m-%d")
            except ValueError as e:
                return {
                    "success": False,
                    "error": f"Invalid date format. Expected YYYY-MM-DD: {str(e)}",
                }

            # Validate arrival < departure
            if arrival >= departure:
                return {
                    "success": False,
                    "error": "Arrival date must be before departure date",
                }

            # Validate guest counts
            if num_adult < 1:
                return {
                    "success": False,
                    "error": "At least one adult is required",
                }

            if num_child is not None and num_child < 0:
                return {
                    "success": False,
                    "error": "Number of children cannot be negative",
                }

            resources = get_resources()
            client = resources.beds24_client
            cache = resources.cache_manager

            # Build booking object
            booking_data: dict[str, Any] = {
                "propertyId": property_id,
                "roomId": room_id,
                "status": status,
                "arrival": arrival,
                "departure": departure,
                "numAdult": num_adult,
                "firstName": first_name,
                "lastName": last_name,
                "email": email,
            }

            # Add optional fields
            if num_child is not None:
                booking_data["numChild"] = num_child
            if title:
                booking_data["title"] = title
            if mobile:
                booking_data["mobile"] = mobile
            if phone:
                booking_data["phone"] = phone
            if address:
                booking_data["address"] = address
            if city:
                booking_data["city"] = city
            if state:
                booking_data["state"] = state
            if postcode:
                booking_data["postcode"] = postcode
            if country:
                booking_data["country"] = country
            if channel:
                booking_data["channel"] = channel
            if api_reference:
                booking_data["apiReference"] = api_reference
            if comment:
                booking_data["comment"] = comment

            # Make API request (POST with array of bookings)
            response = await client.post("/bookings", [booking_data])

            if not response.get("success"):
                error_msg = response.get("error") or response.get("message") or "Unknown error"
                logger.error(f"Failed to create booking: {error_msg}")
                return {
                    "success": False,
                    "error": f"Failed to create booking: {error_msg}",
                }

            # Invalidate all booking caches
            cache.invalidate_bookings()
            logger.info("Invalidated booking caches after creation")

            # Return created booking
            created_bookings = response.get("data", [])
            created_booking = created_bookings[0] if created_bookings else None

            return {
                "success": True,
                "data": created_booking,
                "metadata": {"cache_invalidated": True},
            }

        except Exception as e:
            logger.error(f"Error in create_booking: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
            }

    @mcp.tool()
    async def search_bookings(
        search_string: str, property_id: int | None = None
    ) -> dict[str, Any]:
        """
        Search bookings by guest name, email, or reference.

        Searches across booking guest names, emails, and references.
        Results are cached for 5 minutes.

        Args:
            search_string: Search term (guest name, email, reference, etc.) - REQUIRED
            property_id: Filter results to specific property (optional)

        Returns:
            List of bookings matching the search criteria
        """
        from src.server import get_resources

        try:
            if not search_string or not search_string.strip():
                return {
                    "success": False,
                    "error": "search_string is required and cannot be empty",
                }

            resources = get_resources()
            client = resources.beds24_client
            cache = resources.cache_manager

            # Build query parameters
            query_params: dict[str, Any] = {
                "searchString": search_string.strip(),
                "includeInvoiceItems": True,
                "includeInfoItems": True,
            }

            if property_id:
                query_params["propertyId"] = property_id

            # Generate cache key
            cache_key = cache.make_query_key("search_bookings", query_params)

            # Check cache
            cached = cache.get_bookings_query(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for search_bookings: {search_string}")
                return {
                    "success": True,
                    "data": cached,
                    "metadata": {"cached": True},
                }

            # Make API request
            response = await client.get("/bookings", query_params)

            if not response.get("success"):
                error_msg = response.get("error") or response.get("message") or "Unknown error"
                logger.error(f"Failed to search bookings: {error_msg}")
                return {
                    "success": False,
                    "error": f"Failed to search bookings: {error_msg}",
                }

            search_results = response.get("data", [])

            # Cache results
            cache.cache_bookings_query(cache_key, search_results)

            return {
                "success": True,
                "data": search_results,
                "metadata": {"cached": False, "count": len(search_results)},
            }

        except Exception as e:
            logger.error(f"Error in search_bookings: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
            }

    logger.info("Registered 6 booking tools")
