from pydantic_ai import RunContext
from PydanticAI.deps import SystemDeps
from typing import Dict, Any, List, Optional
import asyncio
from datetime import datetime, timedelta
import json
import requests

import re

# --- Helper for Datetime Serialization ---
def _serialize(obj: Any) -> Any:
    if isinstance(obj, (datetime, str, int, float, bool, type(None))):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if hasattr(obj, '__dict__'):
        return _serialize(obj.__dict__)
    return str(obj)

def _normalize_str(s: str) -> str:
    """Normalize string for fuzzy matching (lowercase, remove all non-alphanumeric characters)."""
    if not s: return ""
    # Remove all non-alphanumeric characters (including hyphens, spaces, underscores, #, etc.)
    return re.sub(r'[^a-zA-Z0-9]', '', s.lower())

async def find_device_fuzzy(ctx: RunContext[SystemDeps], name_or_id: str) -> Optional[Dict[str, Any]]:
    """
    Find a device using fuzzy matching on name or ID.
    Prioritizes:
    1. API Exact Match (Name or ID)
    2. DuckDB Exact Match
    3. DuckDB Normalized Fuzzy Match
    """
    api = ctx.deps.geotab_api
    
    # Pre-process input: if it's "Demo-18", also try "Demo - 18" for API search
    search_terms = [name_or_id]
    if '-' in name_or_id and ' ' not in name_or_id:
        search_terms.append(name_or_id.replace('-', ' - '))
    elif ' - ' in name_or_id:
        search_terms.append(name_or_id.replace(' - ', '-'))
        
    # 1. Try API Exact Match first (Fastest if correct)
    try:
        for term in search_terms:
            devices = await asyncio.to_thread(api.get, "Device", search={"name": term})
            if devices: return devices[0]
            
            devices = await asyncio.to_thread(api.get, "Device", search={"id": term})
            if devices: return devices[0]
    except:
        pass # Fallback to DuckDB
        
    # 2. Query DuckDB for all devices
    try:
        df, _ = ctx.deps.duckdb_manager.query("SELECT id, name FROM devices")
        if df.empty: return None
        
        candidates = df.to_dict('records')
        
        target = _normalize_str(name_or_id)
        
        best_match = None
        
        for d in candidates:
            d_name = d.get('name', '')
            d_id = d.get('id', '')
            
            norm_name = _normalize_str(d_name)
            norm_id = _normalize_str(d_id)
            
            # Exact normalized match
            if norm_name == target or norm_id == target:
                return d
            
            # Partial match (contains)
            if target in norm_name or target in norm_id:
                # Keep looking for exact match, but store this as candidate
                if not best_match: 
                    best_match = d
                    
        return best_match
        
    except Exception as e:
        print(f"Fuzzy search error: {e}")
        return None

def log_tool_start(ctx: RunContext[SystemDeps], tool_name: str, args: Any):
    if ctx.deps.on_log:
        ctx.deps.on_log({
            "type": "tool_call",
            "title": f"Calling Tool: {tool_name}",
            "content": str(args),
            "icon": "fa-tools"
        })

def log_tool_end(ctx: RunContext[SystemDeps], tool_name: str, result: Any):
    if ctx.deps.on_log:
        ctx.deps.on_log({
            "type": "tool_result",
            "title": f"Result: {tool_name}",
            "content": str(result),
            "icon": "fa-check-circle"
        })

# --- Geotab Tools ---

async def get_fleet_overview(ctx: RunContext[SystemDeps]) -> str:
    """
    Get a high-level overview of the fleet (total vehicles, active count).
    """
    log_tool_start(ctx, "get_fleet_overview", {})
    api = ctx.deps.geotab_api
    try:
        devices = await asyncio.to_thread(api.get, "Device")
        total = len(devices)
        # Simple active check (this is a mock logic, real logic needs StatusData)
        result = f"Fleet Overview: Total Vehicles: {total}. (Active count requires StatusData query)"
        log_tool_end(ctx, "get_fleet_overview", result)
        return result
    except Exception as e:
        log_tool_end(ctx, "get_fleet_overview", f"Error: {e}")
        return f"Error fetching fleet overview: {e}"

async def get_vehicle_location(ctx: RunContext[SystemDeps], device_id: str) -> Dict[str, Any]:
    """
    Get the current location of a specific vehicle.
    Args:
        device_id: The ID or Name of the vehicle (e.g., 'b1' or 'Demo - 21').
    """
    log_tool_start(ctx, "get_vehicle_location", {"device_id": device_id})
    api = ctx.deps.geotab_api
    try:
        # 1. Resolve Device ID (Fuzzy)
        device = await find_device_fuzzy(ctx, device_id)
        
        if not device:
            err = {"error": f"Vehicle '{device_id}' not found."}
            log_tool_end(ctx, "get_vehicle_location", err)
            return err
            
        real_id = device['id']
        name = device['name']

        # 2. Get LogRecord
        now = datetime.utcnow()
        logs = await asyncio.to_thread(api.get, "LogRecord", search={"deviceSearch": {"id": real_id}, "fromDate": now - timedelta(minutes=10), "toDate": now})
        
        if not logs:
             err = {"error": f"No recent location data for {name}."}
             log_tool_end(ctx, "get_vehicle_location", err)
             return err
             
        latest = logs[-1]
        
        # 3. Auto-Plot on Map
        cmd = {
            "type": "marker",
            "data": {
                "lat": latest['latitude'],
                "lon": latest['longitude'],
                "title": name,
                "snippet": f"Speed: {latest['speed']} km/h",
                "icon": "truck"
            }
        }
        ctx.deps.map_commands.append(cmd)
        
        result = {
            "id": real_id,
            "name": name,
            "latitude": latest['latitude'],
            "longitude": latest['longitude'],
            "speed": latest['speed'],
            "dateTime": latest['dateTime'].isoformat(),
            "note": "Vehicle location has been plotted on the map."
        }
        log_tool_end(ctx, "get_vehicle_location", result)
        return result
    except Exception as e:
        log_tool_end(ctx, "get_vehicle_location", f"Error: {e}")
        return {"error": str(e)}

async def get_vehicle_history(ctx: RunContext[SystemDeps], device_id: str, date: str) -> Dict[str, Any]:
    """
    Get historical route logs and events for a vehicle on a specific date.
    Args:
        device_id: Vehicle ID or Name.
        date: YYYY-MM-DD string.
    """
    log_tool_start(ctx, "get_vehicle_history", {"device_id": device_id, "date": date})
    api = ctx.deps.geotab_api
    try:
        # 1. Resolve Device (Fuzzy)
        device = await find_device_fuzzy(ctx, device_id)
        
        if not device:
            err = {"error": f"Vehicle '{device_id}' not found."}
            log_tool_end(ctx, "get_vehicle_history", err)
            return err
        real_id = device['id']
        name = device['name']
        
        # 2. Get Logs
        try:
            from_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            # Handle invalid date (e.g., 2026-02-29)
            return {"error": f"Invalid date format or value: {date}"}
            
        to_date = from_date + timedelta(days=1)
        
        logs = await asyncio.to_thread(api.get, "LogRecord", search={"deviceSearch": {"id": real_id}, "fromDate": from_date, "toDate": to_date})
        
        # 3. Auto-Visualize Route
        if logs:
            path_points = [[l['latitude'], l['longitude']] for l in logs]
            
            # Create Map Command directly
            start_time = logs[0]['dateTime'].strftime('%H:%M')
            end_time = logs[-1]['dateTime'].strftime('%H:%M')
            
            cmd = {
                "type": "route",
                "data": {
                    "path": path_points,
                    "color": "#e74c3c", # Red for history
                    "origin": "Start",
                    "origin_label": f"Start ({start_time})",
                    "destination": "End",
                    "destination_label": f"End ({end_time})"
                }
            }
            ctx.deps.map_commands.append(cmd)
            log_tool_end(ctx, "get_vehicle_history", f"Auto-plotted {len(logs)} points for {name}")
        
        # 4. Get Events (Mock for now, or implement ExceptionEvent query)
        events = [] 
        
        result = {
            "device_id": real_id,
            "device_name": name,
            "date": date,
            "logs_count": len(logs),
            "note": "Route has been automatically plotted on the map.",
            "events": _serialize(events)
        }
        return result
    except Exception as e:
        log_tool_end(ctx, "get_vehicle_history", f"Error: {e}")
        return {"error": str(e)}

async def get_vehicles_risk_data(ctx: RunContext[SystemDeps], date: Optional[str] = None) -> str:
    """
    Get risk/safety analysis for the fleet, specifically identifying top violators and risky drivers.
    Args:
        date: Optional YYYY-MM-DD date to filter the analysis.
    """
    log_tool_start(ctx, "get_vehicles_risk_data", {"date": date})
    
    try:
        # Construct Query
        # We query the 'events' table which contains rule violations
        
        where_clause = ""
        if date:
            # activeFrom is VARCHAR, likely ISO format. We can try to match the date part.
            # activeFrom LIKE '2026-02-27%'
            # Fix: Cast TIMESTAMP to VARCHAR for LIKE operator in DuckDB
            where_clause = f"WHERE CAST(e.activeFrom AS VARCHAR) LIKE '{date}%'"
            
        # Updated query to include baseType to distinguish between safety/compliance and vehicle health
        # baseType examples: 'Safety', 'VehicleHealth', 'Compliance', 'Productivity'
        # If baseType is missing in rules table, we might need to rely on rule name heuristics
        
        # We also want to get location if available. 
        # Since 'events' table might not have location populated in our mock preload, we can try to join with logs?
        # A simple join on device_id and closest time is complex in SQL without ASOF JOIN (DuckDB supports it!)
        # Let's try ASOF JOIN if we have logs.
        
        # NOTE: ASOF JOIN requires both tables to be sorted by time.
        # AND DuckDB syntax: SELECT ... FROM events ASOF JOIN logs ON events.device_id = logs.device_id AND events.activeFrom >= logs.dateTime
        
        # For simplicity and robustness, let's just get the top violators first.
        # If the user asks for "location", we might need a separate tool or a more complex query here.
        # The user's prompt "show me the speeding location of Demo-18" might trigger 'get_vehicle_location' or 'get_vehicle_history'.
        # But this tool 'get_vehicles_risk_data' is for "top violators".
        
        # Wait, if the user asks for "speeding location of Demo-18", the Agent might call this tool if it thinks it's about risk?
        # Or it should call a tool to get specific event locations.
        # Let's make this tool return location hints if possible.
        
        query = f"""
            SELECT 
                d.name as device_name, 
                e.device_id, 
                COUNT(*) as violation_count,
                STRING_AGG(DISTINCT r.name || ' (' || COALESCE(r.baseType, 'Unknown') || ')', ', ') as rules_broken
            FROM events e
            LEFT JOIN devices d ON e.device_id = d.id
            LEFT JOIN rules r ON e.rule_id = r.id
            {where_clause}
            GROUP BY e.device_id, d.name
            ORDER BY violation_count DESC
            LIMIT 5
        """
        
        df, _ = ctx.deps.duckdb_manager.query(query)
        
        if df.empty:
            msg = f"No risk data (violations) found{' for ' + date if date else ''}."
            log_tool_end(ctx, "get_vehicles_risk_data", msg)
            return msg
            
        # Format output
        records = df.to_dict('records')
        summary = f"Top Violators{' (' + date + ')' if date else ''}:\n"
        
        for i, r in enumerate(records, 1):
            name = r.get('device_name') or r.get('device_id') or 'Unknown'
            count = r.get('violation_count')
            rules = r.get('rules_broken') or 'Unknown Rules'
            summary += f"{i}. {name}: {count} violations\n   Details: {rules}\n"
            
        log_tool_end(ctx, "get_vehicles_risk_data", summary)
        return summary
        
    except Exception as e:
        log_tool_end(ctx, "get_vehicles_risk_data", f"Error: {e}")
        return f"Error analyzing risk data: {e}"

async def get_vehicle_event_locations(ctx: RunContext[SystemDeps], device_id: str, date: str, event_type: Optional[str] = None) -> str:
    """
    Get AND PLOT the locations where specific violations/events occurred for a vehicle on the map.
    Use this tool when the user asks to "show violations on map" or "where did the speeding happen?".
    
    Args:
        device_id: Vehicle ID or Name (e.g., 'Demo - 18').
        date: YYYY-MM-DD string.
        event_type: Optional filter (e.g., 'Speeding', 'Harsh Braking'). If None, returns all events.
    """
    log_tool_start(ctx, "get_vehicle_event_locations", {"device_id": device_id, "date": date, "event_type": event_type})
    
    try:
        # 1. Resolve Device
        device = await find_device_fuzzy(ctx, device_id)
        if not device:
            return f"Vehicle '{device_id}' not found."
        real_id = device['id']
        name = device['name']
        
        # 2. Query Events and Join with Logs (ASOF JOIN) to get location
        # DuckDB ASOF JOIN is powerful here.
        # We need to ensure timestamps are compatible.
        
        event_filter = ""
        if event_type:
            event_filter = f"AND r.name ILIKE '%{event_type}%'"
            
        query = f"""
            WITH target_events AS (
                SELECT 
                    e.activeFrom, 
                    e.duration, 
                    r.name as rule_name,
                    e.device_id
                FROM events e
                JOIN rules r ON e.rule_id = r.id
                WHERE e.device_id = '{real_id}' 
                AND CAST(e.activeFrom AS VARCHAR) LIKE '{date}%'
                {event_filter}
                ORDER BY e.activeFrom
            ),
            target_logs AS (
                SELECT dateTime, latitude, longitude
                FROM logs
                WHERE device_id = '{real_id}'
                ORDER BY dateTime
            )
            SELECT 
                e.activeFrom, 
                e.rule_name,
                l.latitude,
                l.longitude
            FROM target_events e
            ASOF JOIN target_logs l ON e.activeFrom >= l.dateTime
            WHERE l.dateTime >= e.activeFrom - INTERVAL 5 MINUTE -- Ensure log is close enough
        """
        
        df, _ = ctx.deps.duckdb_manager.query(query)
        
        if df.empty:
            msg = f"No event locations found for {name} on {date} (Data might be missing or no matching logs)."
            log_tool_end(ctx, "get_vehicle_event_locations", msg)
            return msg
            
        # Plot on map
        records = df.to_dict('records')
        for r in records:
            lat, lon = r.get('latitude'), r.get('longitude')
            if lat and lon:
                cmd = {
                    "type": "marker",
                    "data": {
                        "lat": lat,
                        "lon": lon,
                        "title": f"{r['rule_name']} ({name})",
                        "snippet": f"Time: {r['activeFrom']}",
                        "icon": "event"
                    }
                }
                ctx.deps.map_commands.append(cmd)
                
        summary = f"Found {len(records)} event locations for {name} on {date}. They have been plotted on the map."
        log_tool_end(ctx, "get_vehicle_event_locations", summary)
        return summary
        
    except Exception as e:
        log_tool_end(ctx, "get_vehicle_event_locations", f"Error: {e}")
        return f"Error finding event locations: {e}"

async def check_traffic_incident(ctx: RunContext[SystemDeps], lat: Optional[float] = None, lon: Optional[float] = None, location_name: Optional[str] = None) -> str:
    """
    Check for traffic incidents near a location using TomTom.
    You can provide either (lat, lon) OR a location_name (e.g., "Vigo", "Times Square").
    If location_name is provided, the tool will automatically geocode it.
    """
    log_tool_start(ctx, "check_traffic_incident", {"lat": lat, "lon": lon, "location_name": location_name})
    
    try:
        # Auto-geocode if name provided but coords missing
        if location_name and (lat is None or lon is None):
            client = ctx.deps.gmp_client
            if client:
                places = await asyncio.to_thread(client.places, query=location_name)
                if places and 'results' in places and len(places['results']) > 0:
                    loc = places['results'][0]['geometry']['location']
                    lat = loc['lat']
                    lon = loc['lng']
                    # Auto-plot the search center
                    ctx.deps.map_commands.append({
                        "type": "marker",
                        "data": {
                            "lat": lat, "lon": lon, 
                            "title": location_name, 
                            "icon": "pin"
                        }
                    })
                else:
                    return f"Could not find location '{location_name}' to check traffic."
            else:
                 return "Google Maps Client not available for geocoding."

        if lat is None or lon is None:
            return "Please provide either coordinates (lat, lon) or a location_name."

        incidents = ctx.deps.traffic_service.check_nearby_incidents(lat, lon)
        
        if not incidents:
            msg = "No traffic incidents found nearby."
            log_tool_end(ctx, "check_traffic_incident", msg)
            return msg
            
        # Auto-plot incidents on map
        for inc in incidents:
            try:
                coords = inc.get('coordinates')
                # TomTom returns [lon, lat] for points in GeoJSON, or lines
                # The service returns 'coordinates' which is the geometry coordinates
                # We need to handle Point vs LineString.
                # Assuming Point for simplicity or taking first point of LineString
                
                plot_lat, plot_lon = lat, lon # Default to search center if geometry missing
                
                if coords:
                    # Check if it's a list of floats (Point) or list of lists (LineString)
                    if isinstance(coords[0], float):
                        plot_lon, plot_lat = coords[0], coords[1]
                    elif isinstance(coords[0], list):
                        plot_lon, plot_lat = coords[0][0], coords[0][1]
                
                description = inc.get('description', 'Traffic Incident')
                category = inc.get('category')
                magnitude = inc.get('magnitude', 0)
                
                # Create marker command
                cmd = {
                    "type": "marker",
                    "data": {
                        "lat": plot_lat,
                        "lon": plot_lon,
                        "title": description,
                        "snippet": f"Type: {category}, Delay: {magnitude}s",
                        "icon": "event" # Use event icon or fallback
                    }
                }
                ctx.deps.map_commands.append(cmd)
            except Exception as e:
                print(f"Error plotting incident: {e}")
            
        # Format for AI consumption
        summary = f"Found {len(incidents)} incidents:\n"
        for inc in incidents:
            summary += f"- [{inc.get('category')}] {inc.get('description')} (Delay: {inc.get('magnitude')}s)\n"
        summary += "\n(All incidents have been auto-plotted on the map)"
            
        log_tool_end(ctx, "check_traffic_incident", f"Found {len(incidents)} incidents")
        return summary
    except Exception as e:
        log_tool_end(ctx, "check_traffic_incident", f"Error: {e}")
        return f"Traffic check failed: {e}"

async def query_fleet_events(ctx: RunContext[SystemDeps], query: str) -> str:
    """
    Query specific fleet events using natural language.
    """
    return f"Querying fleet events for: {query} (Mock Response)"

async def ask_geotab_ace_for_data(ctx: RunContext[SystemDeps], question: str) -> str:
    """
    Use Geotab ACE (Advanced Conversational Engine) for complex queries.
    This tool performs a multi-step process: Create Chat -> Send Prompt -> Poll for Results.
    It may take 30-60 seconds to complete.
    """
    log_tool_start(ctx, "ask_geotab_ace_for_data", {"question": question})
    api = ctx.deps.geotab_api
    service_name = 'dna-planet-orchestration'
    
    # Helper to execute raw JSON-RPC via requests (Bypassing SDK wrapper for Ace compatibility)
    def raw_rpc_call(method, params):
        # Fix: Use api.credentials.server instead of api.server
        server = getattr(api, 'server', None) or getattr(api.credentials, 'server', None)
        if not server:
            return {"error": "API Server not found in credentials."}
            
        url = f"https://{server}/apiv1"
        
        # Ensure credentials are included
        # Fix: Robustly extract credentials from mygeotab API object
        if 'credentials' not in params:
            creds = {}
            if hasattr(api.credentials, 'database'): creds['database'] = api.credentials.database
            if hasattr(api.credentials, 'username'): creds['userName'] = api.credentials.username
            
            # CRITICAL FIX: The attribute is 'session_id' (snake_case) in the SDK object, 
            # but the JSON-RPC API expects 'sessionId' (camelCase).
            if hasattr(api.credentials, 'session_id'): 
                creds['sessionId'] = api.credentials.session_id
            elif hasattr(api.credentials, 'sessionId'): 
                creds['sessionId'] = api.credentials.sessionId
            
            # Fallback for dictionary-like access if attributes fail
            if not creds.get('sessionId') and hasattr(api.credentials, 'get'):
                creds['database'] = api.credentials.get('database')
                creds['userName'] = api.credentials.get('username') or api.credentials.get('userName')
                creds['sessionId'] = api.credentials.get('sessionId') or api.credentials.get('session_id')

            if not creds.get('sessionId'):
                 return {"error": "Invalid Credentials: No sessionId found"}

            params['credentials'] = creds
            
        payload = {
            "method": method,
            "params": params
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            
            # Check for JSON-RPC Error in response body
            json_resp = resp.json()
            if 'error' in json_resp:
                return {"error": json_resp['error']}
                
            return json_resp
        except Exception as e:
            print(f"Raw RPC Error: {e}")
            return {"error": str(e)}

    try:
        # 1. Create Chat
        # print(f"[ACE] Creating chat...")
        chat_response = await asyncio.to_thread(
            raw_rpc_call, 'GetAceResults',
            {
                "serviceName": service_name,
                "functionName": 'create-chat',
                "customerData": True,
                "functionParameters": {}
            }
        )
        
        if "error" in chat_response:
             err = f"ACE Error (Create Chat): {chat_response['error']}"
             log_tool_end(ctx, "ask_geotab_ace_for_data", err)
             return err

        results = chat_response.get('result', {}).get('apiResult', {}).get('results', [])
        if not results:
            err = "ACE Error: Failed to create chat (No results)."
            log_tool_end(ctx, "ask_geotab_ace_for_data", err)
            return err
            
        chat_id = results[0].get('chat_id')
        if not chat_id:
            err = "ACE Error: No chat_id returned."
            log_tool_end(ctx, "ask_geotab_ace_for_data", err)
            return err
            
        # 2. Send Prompt
        # print(f"[ACE] Sending prompt: {question}")
        prompt_response = await asyncio.to_thread(
            raw_rpc_call, 'GetAceResults',
            {
                "serviceName": service_name,
                "functionName": 'send-prompt',
                "customerData": True,
                "functionParameters": {
                    "chat_id": chat_id,
                    "prompt": question
                }
            }
        )
        
        if "error" in prompt_response:
             err = f"ACE Error (Send Prompt): {prompt_response['error']}"
             log_tool_end(ctx, "ask_geotab_ace_for_data", err)
             return err
        
        p_results = prompt_response.get('result', {}).get('apiResult', {}).get('results', [])
        if not p_results:
            err = "ACE Error: Failed to send prompt."
            log_tool_end(ctx, "ask_geotab_ace_for_data", err)
            return err
            
        # Handle different message_group_id locations
        res_data = p_results[0]
        message_group_id = res_data.get('message_group_id') or res_data.get('message_group', {}).get('id')
        
        if not message_group_id:
            err = "ACE Error: No message_group_id returned."
            log_tool_end(ctx, "ask_geotab_ace_for_data", err)
            return err
            
        # 3. Poll for Results
        # print(f"[ACE] Polling for results (Group: {message_group_id})...")
        status = "PROCESSING"
        attempts = 0
        max_attempts = 20 # ~100 seconds max
        
        while status != "DONE" and status != "FAILED" and attempts < max_attempts:
            await asyncio.sleep(5) # Wait 5s between polls
            attempts += 1
            
            poll_response = await asyncio.to_thread(
                raw_rpc_call, 'GetAceResults',
                {
                    "serviceName": service_name,
                    "functionName": 'get-message-group',
                    "customerData": True,
                    "functionParameters": {
                        "chat_id": chat_id,
                        "message_group_id": message_group_id
                    }
                }
            )
            
            if "error" in poll_response:
                 continue # Retry on error?
            
            poll_data = poll_response.get('result', {}).get('apiResult', {}).get('results', [])
            if not poll_data:
                continue
                
            group = poll_data[0].get('message_group', {})
            status = group.get('status', {}).get('status', "PROCESSING")
            
            if status == "DONE":
                messages = group.get('messages', {})
                # Extract the answer from the last message
                # Messages is a dict where keys are IDs. We want the reasoning or preview_array.
                
                final_answer = ""
                preview_data = []
                
                for msg_id, msg_content in messages.items():
                    # Look for reasoning (text answer) and preview_array (data)
                    if 'reasoning' in msg_content:
                        final_answer = msg_content['reasoning']
                    if 'preview_array' in msg_content:
                        preview_data = msg_content['preview_array']
                
                # Format the output
                output = f"ACE Answer: {final_answer}\n"
                if preview_data:
                    output += f"\nData Preview ({len(preview_data)} rows):\n{_serialize(preview_data)}"
                
                # Cache the data in DuckDB if significant? 
                # For now just return string to Agent.
                log_tool_end(ctx, "ask_geotab_ace_for_data", "ACE Query Successful")
                return output
                
            elif status == "FAILED":
                err = "ACE Query Failed."
                log_tool_end(ctx, "ask_geotab_ace_for_data", err)
                return err
        
        err = "ACE Query Timed Out."
        log_tool_end(ctx, "ask_geotab_ace_for_data", err)
        return err

    except Exception as e:
        log_tool_end(ctx, "ask_geotab_ace_for_data", f"Error: {e}")
        return f"ACE Exception: {e}"

async def geotab_query_duckdb(ctx: RunContext[SystemDeps], query: str) -> str:
    """
    Execute a SQL query against the local DuckDB cache of Geotab data.
    Available tables:
    - devices (id, name, serialNumber, deviceType, activeFrom, activeTo)
    - logs (device_id, dateTime, latitude, longitude, speed, rpm, volts)
    - rules (id, name, baseType)
    - events (id, device_id, rule_id, activeFrom, activeTo, duration)
    """
    log_tool_start(ctx, "geotab_query_duckdb", {"query": query})
    try:
        result = ctx.deps.duckdb_manager.query(query)
        res_str = str(result)
        log_tool_end(ctx, "geotab_query_duckdb", res_str[:200] + "..." if len(res_str) > 200 else res_str)
        return res_str
    except Exception as e:
        log_tool_end(ctx, "geotab_query_duckdb", f"Error: {e}")
        return f"SQL Error: {e}"

async def geotab_remember(ctx: RunContext[SystemDeps], content: str) -> str:
    """
    Store a piece of information in the agent's long-term memory.
    """
    log_tool_start(ctx, "geotab_remember", {"content": content})
    # Use 'pattern' as default category for general learnings
    ctx.deps.memory_manager.remember(content, category="pattern") 
    log_tool_end(ctx, "geotab_remember", "Memory stored.")
    return "Memory stored."

async def geotab_recall(ctx: RunContext[SystemDeps], query: str) -> str:
    """
    Recall information from long-term memory.
    """
    log_tool_start(ctx, "geotab_recall", {"query": query})
    memories = ctx.deps.memory_manager.recall(search=query)
    res_str = str(memories)
    log_tool_end(ctx, "geotab_recall", res_str)
    return res_str

# --- GMP Tools ---

async def search_places(ctx: RunContext[SystemDeps], query: str, location: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search for places (e.g., 'gas stations', 'restaurants') using Google Maps.
    Args:
        query: The search query.
        location: Optional 'lat,lon' string or address to bias results.
    """
    log_tool_start(ctx, "search_places", {"query": query, "location": location})
    client = ctx.deps.gmp_client
    if not client:
        err = [{"error": "Google Maps Client not initialized"}]
        log_tool_end(ctx, "search_places", err)
        return err
    
    try:
        # Simple text search
        # If location is provided, use it!
        kwargs = {"query": query}
        if location:
            try:
                # location is "lat,lon" string
                parts = location.split(',')
                if len(parts) == 2:
                    lat, lng = float(parts[0]), float(parts[1])
                    kwargs["location"] = (lat, lng)
                    kwargs["radius"] = 5000 # 5km default
            except:
                pass # Ignore if invalid format
        
        result = await asyncio.to_thread(client.places, **kwargs)
        
        places = []
        if result and 'results' in result:
            for p in result['results'][:5]: # Top 5
                places.append({
                    "name": p['name'],
                    "address": p.get('formatted_address'),
                    "lat": p['geometry']['location']['lat'],
                    "lng": p['geometry']['location']['lng'],
                    "rating": p.get('rating')
                })
        log_tool_end(ctx, "search_places", f"Found {len(places)} places")
        return places
    except Exception as e:
        log_tool_end(ctx, "search_places", f"Error: {e}")
        return [{"error": str(e)}]

async def compute_routes(ctx: RunContext[SystemDeps], origin: str, destination: str) -> Dict[str, Any]:
    """
    Compute a route between two points.
    Args:
        origin: Address or 'lat,lon'.
        destination: Address or 'lat,lon'.
    """
    log_tool_start(ctx, "compute_routes", {"origin": origin, "destination": destination})
    client = ctx.deps.gmp_client
    if not client:
        err = {"error": "Google Maps Client not initialized"}
        log_tool_end(ctx, "compute_routes", err)
        return err
        
    try:
        directions = await asyncio.to_thread(client.directions, origin, destination, mode="driving")
        
        if not directions:
            err = {"error": "No route found"}
            log_tool_end(ctx, "compute_routes", err)
            return err
            
        route = directions[0]
        leg = route['legs'][0]
        
        result = {
            "summary": route.get('summary'),
            "distance": leg['distance']['text'],
            "duration": leg['duration']['text'],
            "start_address": leg['start_address'],
            "end_address": leg['end_address'],
            "overview_polyline": route['overview_polyline']['points']
        }
        
        # Auto-plot route on map
        cmd = {
            "type": "route",
            "data": {
                "path": route['overview_polyline']['points'],
                "color": "#3498db",
                "origin": origin,
                "destination": destination
            }
        }
        ctx.deps.map_commands.append(cmd)
        
        log_tool_end(ctx, "compute_routes", f"Route found: {result['distance']}, {result['duration']}")
        return result
    except Exception as e:
        log_tool_end(ctx, "compute_routes", f"Error: {e}")
        return {"error": str(e)}

# --- Map Rendering Tool ---

async def render_map_tool(ctx: RunContext[SystemDeps], type: str, data: Dict[str, Any]) -> str:
    """
    Render items on the frontend map.
    Args:
        type: 'marker', 'route', or 'clear'.
        data: The data for the command.
            - For 'marker': {'lat': float, 'lon': float, 'title': str, 'icon': 'truck'|'pin'}
            - For 'route': {'path': str (encoded polyline), 'origin': str, 'destination': str}
            - For 'clear': {}
    """
    log_tool_start(ctx, "render_map_tool", {"type": type, "data": data})
    # Validate and clean data
    clean_data = _serialize(data)
    
    command = {"type": type, "data": clean_data}
    ctx.deps.map_commands.append(command)
    
    log_tool_end(ctx, "render_map_tool", "Command queued")
    return f"Map command '{type}' added to queue."
