# Beds24 MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server for the [Beds24](https://beds24.com) API v2, built with [FastMCP](https://gofastmcp.com). It lets an MCP client such as Claude work with bookings, properties, availability, messages and calendars.

## Tools

| Area | Tools |
|---|---|
| Bookings | `get_bookings`, `get_booking`, `search_bookings`, `get_arrivals`, `get_departures`, `create_booking` |
| Properties | `get_properties`, `get_property_rooms` |
| Availability | `check_availability`, `get_best_price` |
| Messages | `get_messages`, `get_unread_messages`, `send_message`, `add_internal_note` |
| Calendar | `get_calendar`, `update_pricing`, `set_availability`, `block_dates` |

Some tools change live data. Limit what the server can do by choosing the scopes on your Beds24 token.

## Get a Beds24 refresh token

1. In Beds24, go to Settings → Marketplace → API and generate an invite code with the scopes you need.
2. Exchange it for a refresh token. Each invite code works once:

   ```bash
   curl -s -H "code: YOUR_INVITE_CODE" https://beds24.com/api/v2/authentication/setup
   ```

3. Use the `refreshToken` value from the reply, not the `token` value.

## Configuration

Copy `.env.example` to `.env` and fill it in. Never commit `.env`.

| Variable | Required | Description |
|---|---|---|
| `BEDS24_REFRESH_TOKEN` | Yes | Beds24 refresh token |
| `MCP_TRANSPORT` | No | `stdio` (default) or `http`. Use `http` when deploying. |
| `LOG_LEVEL` | No | Defaults to `INFO` |

## Run locally

Requires Python 3.11 or later.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m src.main
```

## Deploy

The server deploys to any FastMCP host. On [Prefect Horizon](https://www.prefect.io/horizon), use the entrypoint `server.py` and set the variables above in the Production environment. Turn on authentication, because the server can read guest data.

## Rate limits

The client sends one request at a time with a delay between requests, and caches responses, to stay within Beds24's API limits.
