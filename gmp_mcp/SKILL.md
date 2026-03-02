---
name: google-maps-mcp-integration
description: Complete guide for AI assistants to integrate the official Google Maps Platform (GMP) Remote MCP Server. Use this skill to add real-world location context (places, routing, weather) and orchestrate it with Geotab fleet data.
license: Apache-2.0
metadata:
  author: Gordon So (Master Concept)
  version: "1.0"
---

# Google Maps Platform (GMP) MCP Integration Guide

This skill provides the necessary context, schemas, and orchestration patterns to integrate the Google Maps MCP Server into our existing Web App, specifically to work alongside the Geotab MCP.

## 1. Server Endpoint & Setup

Google offers a fully-managed, remote MCP server for Maps Grounding Lite.
- **Endpoint URL**: `https://mapstools.googleapis.com/mcp`
- **Connection Type**: Streamable HTTP (Remote)
- **Requirement**: Must have a valid Google Cloud API Key with Maps Platform enabled.

### Client Configuration Pattern
For MCP clients (like Claude Desktop or custom LangChain/Agent setups), the server is registered as follows:
```json
{
  "mcpServers": {
    "google-maps": {
      "type": "http",
      "url": "https://mapstools.googleapis.com/mcp"
    }
  }
}
2. Available Core Tools
The server exposes three primary tools. CRITICAL: Strictly follow the parameter structures.
Tool 1: search_places
Finds places, businesses, addresses, or points of interest.
text_query (string, MANDATORY): The primary search query (e.g., 'heavy duty truck repair', '1600 Amphitheatre Pkwy').
location_bias (object, OPTIONAL): Prioritizes results near a geographic area.
Pattern: {"circle": {"center": {"latitude": [float], "longitude": [float]}, "radius_meters": [integer]}}
Tool 2: compute_routes
Computes travel routes, distance, and ETA (Expected Time of Arrival) between points.
origin & destination (MANDATORY): Both must be provided. Each can be ONE of the following formats:
address: string (e.g., 'Eiffel Tower, Paris')
lat_lng: object {"latitude": float, "longitude": float}
place_id: string (obtained from search_places)
travel_mode (string, OPTIONAL): DRIVE (default) or WALK.
Tool 3: lookup_weather
Retrieves current conditions, hourly, and daily forecasts.
location (MANDATORY): MUST provide exactly ONE of the following sub-fields:
lat_lng: object {"latitude": float, "longitude": float}
place_id: string
address: string (Must be specific, including country/region)
date / hour (OPTIONAL): Leave both empty for Current Weather. Provide date + hour (0-23) for Hourly Forecast (max 48 hours).
unitsSystem (string, OPTIONAL): Defaults to METRIC. Use IMPERIAL if requested.
3. Orchestration Patterns (Geotab + Google Maps)
When the user asks a complex fleet question, use these multi-agent patterns to combine Geotab data with Google Maps MCP.
Pattern A: Autonomous Rescue (Geotab GPS -> Maps Places -> Maps Routing)
Scenario: A vehicle breaks down and needs the nearest repair shop.
Call Geotab MCP (Get.DeviceStatusInfo or LogRecord) to get the vehicle's exact latitude and longitude.
Call Google Maps MCP search_places with text_query: "truck repair" and inject the Geotab coordinates into the location_bias.circle.center.
Extract the place_id of the nearest repair shop from the results.
Call Google Maps MCP compute_routes using the Geotab lat_lng as the origin and the shop's place_id as the destination to get the ETA.
Pattern B: Weather-Aware Dispatching (Geotab Trip -> Maps Weather)
Scenario: Warn drivers of bad weather on their route.
Retrieve vehicle destination or current latitude and longitude from Geotab.
Call Google Maps MCP lookup_weather using the lat_lng.
Check the thunderstormProbability or PrecipitationProbability.
If the probability is high, trigger an alert or suggest a route change.
4. Common Mistakes to Avoid
❌ Mistake: Calling compute_routes with missing origin or destination. ✅ Solution: If the user only says "how far to the repair shop", use Geotab API to dynamically find the vehicle's current location to use as the origin.
❌ Mistake: Searching for general terms like "pizza places" without a location context in search_places. ✅ Solution: Always append the city/region to text_query OR pass the location_bias parameter using the vehicle's current GPS.
❌ Mistake: Using the user's local timezone for lookup_weather. ✅ Solution: All date and hour inputs must be relative to the target location's local time zone.