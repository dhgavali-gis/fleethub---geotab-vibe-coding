---
name: tomtom-traffic-api
description: Comprehensive guide for integrating the TomTom Traffic API. Use this skill when you need to fetch real-time traffic incidents (accidents, road closures), flow segment data (current speed vs free-flow speed), or render traffic map tiles.
license: Apache-2.0
metadata:
  author: Gordon So (Master Concept)
  version: "1.0"
---

# TomTom Traffic API Integration Skill

This skill teaches the AI how to correctly construct requests to the TomTom Traffic API to retrieve real-time road conditions, traffic incidents, and map tiles.

## Core Services
1. **Traffic Incidents (v5)**: Fetches accidents, roadworks, and closures inside a Bounding Box (bbox).
2. **Flow Segment Data (v4)**: Fetches the current speed and free-flow speed of the road closest to a specific GPS coordinate.
3. **Raster Tiles (v4)**: Fetches transparent map overlays showing traffic flow or incidents for use in mapping libraries (Leaflet, Folium).

---

## Pattern 1: Incident Details API (v5)
Use this to find what's wrong on the road (accidents, fog, closures) in a specific area.

**Endpoint:** `GET https://{baseURL}/traffic/services/5/incidentDetails`
**BaseURL:** `api.tomtom.com`

**Critical Parameters:**
* `key`: Your TomTom API Key.
* `bbox`: Bounding box `minLon,minLat,maxLon,maxLat` (EPSG:4326).
* `fields`: You **MUST** use a GraphQL-like syntax to specify what fields to return. If omitted, the response is very limited.
* `categoryFilter`: (Optional) Filter by type (e.g., `1` for Accident, `2` for Fog, `6` for Jam, `8` for Road Closed).

**Code Pattern (Python):**
```python
import requests

def get_traffic_incidents(api_key, min_lon, min_lat, max_lon, max_lat):
    # GraphQL-like syntax to request specific fields
    fields = "{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,events{description,code}}}}"
    
    url = "https://api.tomtom.com/traffic/services/5/incidentDetails"
    params = {
        "key": api_key,
        "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "fields": fields,
        "language": "en-US",
        "timeValidityFilter": "present"
    }
    
    response = requests.get(url, params=params)
    return response.json()
Note: iconCategory maps to integers (1=Accident, 2=Fog, 6=Jam, etc.). magnitudeOfDelay maps to integers (0=Unknown, 1=Minor, 2=Moderate, 3=Major, 4=Undefined/Closure).

--------------------------------------------------------------------------------
Pattern 2: Flow Segment Data (v4)
Use this to analyze if a specific vehicle is stuck in traffic or idling on purpose. It returns the current speed and free-flow (ideal) speed of the closest road.
Endpoint: GET https://{baseURL}/traffic/services/4/flowSegmentData/{style}/{zoom}/{format}
• style: Recommended to use absolute or relative0.
• zoom: Recommended 10 (range 0-22).
• format: json
Code Pattern (Python):
def get_flow_segment(api_key, latitude, longitude):
    # Note: point parameter must be "latitude,longitude"
    url = f"https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
    params = {
        "key": api_key,
        "point": f"{latitude},{longitude}",
        "unit": "kmph"
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    if "flowSegmentData" in data:
        current_speed = data["flowSegmentData"]["currentSpeed"]
        free_flow_speed = data["flowSegmentData"]["freeFlowSpeed"]
        return current_speed, free_flow_speed
    return None

--------------------------------------------------------------------------------
Pattern 3: Raster Flow/Incident Tiles (Map Overlays)
Use this to overlay live traffic lines onto map frameworks like Folium or Leaflet.
Flow Tiles URL Template: https://api.tomtom.com/traffic/map/4/tile/flow/relative0/{z}/{x}/{y}.png?key={TOMTOM_API_KEY} (Style relative0 shows red/yellow/green based on congestion compared to free-flow).
Incident Tiles URL Template: https://api.tomtom.com/traffic/map/4/tile/incidents/s0/{z}/{x}/{y}.png?key={TOMTOM_API_KEY}
Code Pattern (Streamlit + Folium):
import folium

def add_tomtom_traffic_to_map(m, tomtom_api_key):
    tiles_url = f"https://api.tomtom.com/traffic/map/4/tile/flow/relative0/{{z}}/{{x}}/{{y}}.png?key={tomtom_api_key}"
    folium.TileLayer(
        tiles=tiles_url,
        attr='TomTom Traffic',
        name='Live Traffic Flow',
        overlay=True,
        control=True
    ).add_to(m)

--------------------------------------------------------------------------------
Pattern 4: Synchronization using Traffic Model ID
Traffic updates every minute. If you call multiple endpoints (e.g., getting Incident Details and then rendering Vector/Raster Tiles), the data might mismatch if an update happened between calls. Solution: Pass the t (Traffic Model ID) parameter.
1. Make your first request without t.
2. Extract TrafficModelID from the HTTP Response Headers.
3. Pass t={TrafficModelID} in all subsequent requests for that user session to ensure the map tiles and incident JSON perfectly match.

--------------------------------------------------------------------------------
❌ Common Mistakes to Avoid
❌ Mistake: Using version 4 for Incident Details. ✅ Correction: Always use version 5 (/services/5/incidentDetails). Version 4 is strictly deprecated.
❌ Mistake: Formatting bbox as lat,lon,lat,lon in Incident Details. ✅ Correction: The bbox parameter MUST be minLon,minLat,maxLon,maxLat (Longitude first).
❌ Mistake: Formatting point as lon,lat in Flow Segment Data. ✅ Correction: The point parameter MUST be latitude,longitude (Latitude first). Note the inconsistency between APIs!
❌ Mistake: Forgetting the fields parameter in Incident Details. ✅ Correction: If you do not explicitly request the nested fields string like {incidents{properties{iconCategory}}}, TomTom will return an almost empty response. You must declare exactly what you want.
❌ Mistake: Trying to fetch too large of a Bounding Box. ✅ Correction: The maximum area of a bounding box is 10,000 km². If you pass a box larger than this, the API returns a 400 Bad Request.
Reference Links
• Traffic API Introduction: https://developer.tomtom.com/traffic-api/documentation/product-information/introduction
• Incident Details (v5): https://developer.tomtom.com/traffic-api/documentation/traffic-incidents/incident-details
• Flow Segment Data: https://developer.tomtom.com/traffic-api/documentation/traffic-flow/flow-segment-data