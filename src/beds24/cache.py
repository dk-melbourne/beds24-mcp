"""
Beds24 Caching Layer
~~~~~~~~~~~~~~~~~~~~

Multi-tier TTL-based caching to reduce API calls and improve performance.

Cache Strategy (TTL per resource type):
- Properties/Rooms: 24 hours (86400s) - rarely change
- Bookings: 5 minutes (300s) - frequently updated
- Availability: 10 minutes (600s) - moderate updates
- Calendar: 15 minutes (900s) - moderate updates
- Messages: NO CACHE - time-sensitive guest communication

Cache Keys:
- Entity: {type}:{id} (e.g., "property:123", "booking:456")
- List: {type}:list (e.g., "properties:list")
- Query: {type}:query:{hash} (e.g., "bookings:query:abc123")

Invalidation Strategy:
- Automatic expiration based on TTL
- Manual invalidation after write operations (create/update/delete)
- Pattern-based invalidation for query caches
"""

from hashlib import md5
from typing import Any

from cachetools import TTLCache

from src.config import settings
from src.logger import get_logger

logger = get_logger(__name__)


class CacheManager:
    """
    Multi-tier caching manager for Beds24 API responses.

    Uses cachetools.TTLCache for automatic expiration and memory-bounded storage.

    Design Principles:
    - Static data (properties, rooms): Long TTL (24h)
    - Dynamic data (bookings): Short TTL (5min)
    - Pricing data (availability, calendar): Medium TTL (10-15min)
    - Real-time data (messages): NO CACHE
    - Invalidate on write operations
    """

    # TTL values in seconds
    TTL_PROPERTIES = 86400  # 24 hours
    TTL_ROOMS = 86400  # 24 hours
    TTL_BOOKINGS = 300  # 5 minutes
    TTL_AVAILABILITY = 600  # 10 minutes
    TTL_CALENDAR = 900  # 15 minutes

    def __init__(self, enabled: bool = True, max_size: int = 1000) -> None:
        """
        Initialize cache manager with configured TTLs.

        Args:
            enabled: Whether caching is enabled (default: True)
            max_size: Maximum number of items per cache tier (default: 1000)
        """
        self._enabled = enabled and settings.cache_enabled

        if not self._enabled:
            logger.info("Caching disabled")
            return

        # TIER 1: Static data (24 hours)
        self._properties_cache: TTLCache[str, Any] = TTLCache(
            maxsize=max_size, ttl=self.TTL_PROPERTIES
        )
        self._rooms_cache: TTLCache[str, Any] = TTLCache(
            maxsize=max_size, ttl=self.TTL_ROOMS
        )

        # TIER 2: Dynamic data (5 minutes)
        self._bookings_cache: TTLCache[str, Any] = TTLCache(
            maxsize=max_size, ttl=self.TTL_BOOKINGS
        )

        # TIER 3: Pricing data (10-15 minutes)
        self._availability_cache: TTLCache[str, Any] = TTLCache(
            maxsize=max_size, ttl=self.TTL_AVAILABILITY
        )
        self._calendar_cache: TTLCache[str, Any] = TTLCache(
            maxsize=max_size, ttl=self.TTL_CALENDAR
        )

        # Messages are NOT cached (handled at service layer)

        # Cache hit/miss statistics
        self._stats = {
            "properties": {"hits": 0, "misses": 0},
            "rooms": {"hits": 0, "misses": 0},
            "bookings": {"hits": 0, "misses": 0},
            "availability": {"hits": 0, "misses": 0},
            "calendar": {"hits": 0, "misses": 0},
        }

        logger.info(
            f"Initialized cache manager with multi-tier TTLs (max_size={max_size})"
        )

    def _get_cache(self, cache_type: str) -> TTLCache[str, Any] | None:
        """
        Get cache tier by type.

        Args:
            cache_type: Cache tier name

        Returns:
            TTLCache instance or None if invalid type
        """
        cache_map = {
            "properties": self._properties_cache,
            "rooms": self._rooms_cache,
            "bookings": self._bookings_cache,
            "availability": self._availability_cache,
            "calendar": self._calendar_cache,
        }
        return cache_map.get(cache_type)

    def get(self, cache_type: str, key: str) -> Any | None:
        """
        Get value from cache.

        Args:
            cache_type: Cache tier (properties, bookings, availability, calendar)
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if not self._enabled:
            return None

        cache = self._get_cache(cache_type)
        if cache is None:
            logger.error(f"Invalid cache type: {cache_type}")
            return None

        value = cache.get(key)

        # Update statistics
        if cache_type in self._stats:
            if value is not None:
                self._stats[cache_type]["hits"] += 1
                logger.debug(f"Cache hit: {cache_type}:{key}")
            else:
                self._stats[cache_type]["misses"] += 1
                logger.debug(f"Cache miss: {cache_type}:{key}")

        return value

    def set(self, cache_type: str, key: str, value: Any) -> None:
        """
        Store value in cache.

        Args:
            cache_type: Cache tier
            key: Cache key
            value: Value to cache
        """
        if not self._enabled:
            return

        cache = self._get_cache(cache_type)
        if cache is None:
            logger.error(f"Invalid cache type: {cache_type}")
            return

        cache[key] = value
        logger.debug(f"Cache set: {cache_type}:{key}")

    def invalidate(self, cache_type: str, key: str | None = None) -> int:
        """
        Invalidate cache entries.

        Args:
            cache_type: Cache tier to invalidate
            key: Specific key to invalidate (None = invalidate all for type)

        Returns:
            Number of entries invalidated
        """
        if not self._enabled:
            return 0

        cache = self._get_cache(cache_type)
        if cache is None:
            logger.error(f"Invalid cache type: {cache_type}")
            return 0

        if key is not None:
            # Invalidate specific key
            if key in cache:
                del cache[key]
                logger.debug(f"Cache invalidated: {cache_type}:{key}")
                return 1
            return 0
        else:
            # Invalidate entire cache tier
            count = len(cache)
            cache.clear()
            logger.info(f"Cache tier cleared: {cache_type} ({count} entries)")
            return count

    def invalidate_pattern(self, cache_type: str, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.

        Args:
            cache_type: Cache tier to search
            pattern: Pattern to match (e.g., "booking:", "query:")

        Returns:
            Number of entries invalidated
        """
        if not self._enabled:
            return 0

        cache = self._get_cache(cache_type)
        if cache is None:
            logger.error(f"Invalid cache type: {cache_type}")
            return 0

        # Find matching keys
        keys_to_delete = [k for k in cache.keys() if isinstance(k, str) and pattern in k]

        # Delete them
        for key in keys_to_delete:
            del cache[key]

        if keys_to_delete:
            logger.info(
                f"Cache pattern invalidated: {cache_type} pattern='{pattern}' "
                f"({len(keys_to_delete)} entries)"
            )

        return len(keys_to_delete)

    # ============================================================================
    # Property Caching (24 hours)
    # ============================================================================

    def cache_property(self, property_id: int, data: Any) -> None:
        """Cache property data (rarely changes)."""
        self.set("properties", f"property:{property_id}", data)

    def get_property(self, property_id: int) -> Any | None:
        """Get cached property data."""
        return self.get("properties", f"property:{property_id}")

    def cache_properties_list(self, data: list[Any]) -> None:
        """Cache full properties list."""
        self.set("properties", "properties:list", data)

    def get_properties_list(self) -> list[Any] | None:
        """Get cached properties list."""
        return self.get("properties", "properties:list")

    def invalidate_property(self, property_id: int) -> None:
        """Invalidate specific property cache."""
        self.invalidate("properties", f"property:{property_id}")
        # Also invalidate properties list
        self.invalidate("properties", "properties:list")

    # ============================================================================
    # Room Caching (24 hours)
    # ============================================================================

    def cache_room(self, room_id: int, data: Any) -> None:
        """Cache room data."""
        self.set("rooms", f"room:{room_id}", data)

    def get_room(self, room_id: int) -> Any | None:
        """Get cached room data."""
        return self.get("rooms", f"room:{room_id}")

    def cache_property_rooms(self, property_id: int, data: list[Any]) -> None:
        """Cache all rooms for a property."""
        self.set("rooms", f"property_rooms:{property_id}", data)

    def get_property_rooms(self, property_id: int) -> list[Any] | None:
        """Get cached rooms for a property."""
        return self.get("rooms", f"property_rooms:{property_id}")

    def invalidate_room(self, room_id: int) -> None:
        """Invalidate specific room cache."""
        self.invalidate("rooms", f"room:{room_id}")

    # ============================================================================
    # Booking Caching (5 minutes)
    # ============================================================================

    def cache_booking(self, booking_id: int, data: Any) -> None:
        """Cache booking data (changes frequently)."""
        self.set("bookings", f"booking:{booking_id}", data)

    def get_booking(self, booking_id: int) -> Any | None:
        """Get cached booking data."""
        return self.get("bookings", f"booking:{booking_id}")

    def cache_bookings_query(self, query_key: str, data: list[Any]) -> None:
        """Cache booking query results."""
        self.set("bookings", f"bookings:query:{query_key}", data)

    def get_bookings_query(self, query_key: str) -> list[Any] | None:
        """Get cached booking query results."""
        return self.get("bookings", f"bookings:query:{query_key}")

    def invalidate_bookings(self) -> None:
        """
        Invalidate all booking-related caches.

        CRITICAL: Call this after creating, updating, or deleting bookings.
        """
        count = self.invalidate_pattern("bookings", "booking")
        logger.info(f"Invalidated all booking caches ({count} entries)")

    def invalidate_booking(self, booking_id: int) -> None:
        """Invalidate specific booking cache."""
        self.invalidate("bookings", f"booking:{booking_id}")
        # Also invalidate query caches as this booking may appear in queries
        self.invalidate_pattern("bookings", "bookings:query:")

    # ============================================================================
    # Availability Caching (10 minutes)
    # ============================================================================

    def cache_availability(self, query_key: str, data: Any) -> None:
        """Cache availability/offers data."""
        self.set("availability", f"availability:{query_key}", data)

    def get_availability(self, query_key: str) -> Any | None:
        """Get cached availability data."""
        return self.get("availability", f"availability:{query_key}")

    def invalidate_availability(self) -> None:
        """
        Invalidate all availability caches.

        Call this after updating pricing or availability.
        """
        count = self.invalidate("availability")
        logger.info(f"Invalidated all availability caches ({count} entries)")

    # ============================================================================
    # Calendar Caching (15 minutes)
    # ============================================================================

    def cache_calendar(self, query_key: str, data: Any) -> None:
        """Cache calendar data."""
        self.set("calendar", f"calendar:{query_key}", data)

    def get_calendar(self, query_key: str) -> Any | None:
        """Get cached calendar data."""
        return self.get("calendar", f"calendar:{query_key}")

    def invalidate_calendar(self) -> None:
        """
        Invalidate all calendar caches.

        Call this after updating pricing, availability, or restrictions.
        Also invalidates availability cache as they're related.
        """
        calendar_count = self.invalidate("calendar")
        avail_count = self.invalidate("availability")
        logger.info(
            f"Invalidated calendar ({calendar_count}) and "
            f"availability ({avail_count}) caches"
        )

    # ============================================================================
    # Query Key Generation
    # ============================================================================

    @staticmethod
    def make_entity_key(entity_type: str, entity_id: int | str) -> str:
        """
        Create cache key for an entity.

        Args:
            entity_type: Type of entity (property, booking, etc.)
            entity_id: Entity identifier

        Returns:
            Cache key string (e.g., "property:123")
        """
        return f"{entity_type}:{entity_id}"

    @staticmethod
    def make_query_key(query_type: str, params: dict[str, Any]) -> str:
        """
        Create deterministic cache key for a query.

        Uses MD5 hash of sorted JSON for consistent, compact keys.

        Args:
            query_type: Type of query (bookings, availability, etc.)
            params: Query parameters dict

        Returns:
            Cache key string (e.g., "bookings:query:a1b2c3d4")

        Example:
            key = cache.make_query_key("bookings", {
                "property_id": 123,
                "arrival_from": "2025-01-01"
            })
            # Returns: "a1b2c3d4e5f6"
        """
        # Sort parameters for consistent keys
        sorted_params = dict(sorted(params.items()))

        # Create stable string representation
        param_str = str(sorted_params)

        # Hash for compact key (first 12 chars of MD5)
        param_hash = md5(param_str.encode()).hexdigest()[:12]

        return param_hash

    def generate_query_key(self, prefix: str, params: dict[str, Any]) -> str:
        """
        Generate cache key from query parameters (legacy method).

        Args:
            prefix: Cache key prefix (e.g., "bookings", "availability")
            params: Query parameters dict

        Returns:
            Cache key string
        """
        return self.make_query_key(prefix, params)

    # ============================================================================
    # Cache Statistics
    # ============================================================================

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics for monitoring.

        Returns:
            Dict with stats for each cache tier including:
            - size: Current number of entries
            - maxsize: Maximum capacity
            - ttl: Time-to-live in seconds
            - hits: Number of cache hits
            - misses: Number of cache misses
            - hit_rate: Percentage of hits
        """
        if not self._enabled:
            return {"enabled": False}

        def calc_hit_rate(hits: int, misses: int) -> float:
            total = hits + misses
            return (hits / total * 100) if total > 0 else 0.0

        return {
            "enabled": True,
            "properties": {
                "size": len(self._properties_cache),
                "maxsize": self._properties_cache.maxsize,
                "ttl": self._properties_cache.ttl,
                "hits": self._stats["properties"]["hits"],
                "misses": self._stats["properties"]["misses"],
                "hit_rate": calc_hit_rate(
                    self._stats["properties"]["hits"],
                    self._stats["properties"]["misses"],
                ),
            },
            "rooms": {
                "size": len(self._rooms_cache),
                "maxsize": self._rooms_cache.maxsize,
                "ttl": self._rooms_cache.ttl,
                "hits": self._stats["rooms"]["hits"],
                "misses": self._stats["rooms"]["misses"],
                "hit_rate": calc_hit_rate(
                    self._stats["rooms"]["hits"],
                    self._stats["rooms"]["misses"],
                ),
            },
            "bookings": {
                "size": len(self._bookings_cache),
                "maxsize": self._bookings_cache.maxsize,
                "ttl": self._bookings_cache.ttl,
                "hits": self._stats["bookings"]["hits"],
                "misses": self._stats["bookings"]["misses"],
                "hit_rate": calc_hit_rate(
                    self._stats["bookings"]["hits"],
                    self._stats["bookings"]["misses"],
                ),
            },
            "availability": {
                "size": len(self._availability_cache),
                "maxsize": self._availability_cache.maxsize,
                "ttl": self._availability_cache.ttl,
                "hits": self._stats["availability"]["hits"],
                "misses": self._stats["availability"]["misses"],
                "hit_rate": calc_hit_rate(
                    self._stats["availability"]["hits"],
                    self._stats["availability"]["misses"],
                ),
            },
            "calendar": {
                "size": len(self._calendar_cache),
                "maxsize": self._calendar_cache.maxsize,
                "ttl": self._calendar_cache.ttl,
                "hits": self._stats["calendar"]["hits"],
                "misses": self._stats["calendar"]["misses"],
                "hit_rate": calc_hit_rate(
                    self._stats["calendar"]["hits"],
                    self._stats["calendar"]["misses"],
                ),
            },
        }

    def clear_all(self) -> None:
        """Clear all caches (use sparingly, for testing)."""
        if not self._enabled:
            return

        total = 0
        total += self.invalidate("properties")
        total += self.invalidate("rooms")
        total += self.invalidate("bookings")
        total += self.invalidate("availability")
        total += self.invalidate("calendar")

        logger.warning(f"Cleared ALL caches ({total} total entries)")

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        for cache_type in self._stats:
            self._stats[cache_type] = {"hits": 0, "misses": 0}
        logger.info("Cache statistics reset")
