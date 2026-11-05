"""
Beds24 MCP Tools
~~~~~~~~~~~~~~~~

18 MCP tool implementations for Beds24 property management:

Bookings (6 tools):
- get_bookings: List bookings with filters
- get_booking: Get single booking by ID
- get_arrivals: Get today's/upcoming arrivals
- get_departures: Get today's/upcoming departures
- create_booking: Create new booking
- search_bookings: Search bookings by guest/reference

Properties (2 tools):
- get_properties: List all properties
- get_property_rooms: Get rooms for a property

Availability (2 tools):
- check_availability: Check room availability
- get_best_price: Get best available price

Messages (4 tools):
- get_messages: Get booking messages
- get_unread_messages: Get unread messages
- send_message: Send message to guest
- add_internal_note: Add internal note to booking

Calendar (4 tools):
- get_calendar: Get calendar data
- update_pricing: Update room pricing
- set_availability: Set room availability
- block_dates: Block dates for a room
"""
