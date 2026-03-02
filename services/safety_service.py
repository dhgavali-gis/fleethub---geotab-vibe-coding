from datetime import datetime, timedelta, timezone
from mygeotab.exceptions import MyGeotabException
import mygeotab
from collections import Counter, defaultdict
import statistics
from typing import List

# Define Rule Categories
DRIVER_RULES = {
    'RuleJackrabbitStartsId',   # Hard Acceleration
    'RuleHarshBrakingId',       # Harsh Braking
    'RuleHarshCorneringId',     # Harsh Cornering
    'RulePostedSpeedingId',     # Speeding
    'aehsazcsCKUi7VK79SxT6gA',  # Max Speed (Custom)
    'RuleSeatbeltId',           # Seat belt
    'RuleIdlingId'              # Idling
}

VEHICLE_RULES = {
    'a6ewYX-gcLUyL01olqgUQBw',  # Engine Fault Exception (Custom)
    'RuleEngineLightOnId'       # Engine Light On
}

CRITICAL_RULES = {
    'RuleEnhancedMajorCollisionId', 
    'RuleEnhancedMinorCollisionId', 
    'RuleAccidentId' 
}

def _fetch_fleet_events(api, days=7):
    """Helper to fetch all events for the last N days."""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    print(f"[SafetyService] Fetching fleet events from {start_date} to {end_date}")
    events = api.get('ExceptionEvent', search={
        'fromDate': start_date,
        'toDate': end_date
    })
    return events

def _get_id(obj):
    """Helper to safely get ID from a dictionary or string."""
    if isinstance(obj, dict):
        return obj.get('id', str(obj))
    return str(obj)

def _resolve_names(api, events):
    """Helper to resolve Rule, Device, and User names."""
    # unique IDs
    rule_ids = set(_get_id(e.get('rule')) for e in events if e.get('rule'))
    device_ids = set(_get_id(e.get('device')) for e in events if e.get('device'))
    user_ids = set()
    for e in events:
        if 'driver' in e:
            user_ids.add(_get_id(e['driver']))
        elif 'user' in e:
            user_ids.add(_get_id(e['user']))
            
    # Fetch objects
    # Note: mygeotab search usually doesn't support list of IDs for 'id' field.
    # Fetching all is safer for Rule/Device/User in this context to avoid JsonSerializerException.
    try:
        rules = api.get('Rule')
        devices = api.get('Device')
        users = api.get('User')
    except Exception as e:
        print(f"[SafetyService] Error resolving names: {e}")
        rules, devices, users = [], [], []
    
    return {
        'rules': {r['id']: r.get('name', r['id']) for r in rules},
        'devices': {d['id']: d.get('name', 'Unknown Device') for d in devices},
        'users': {u['id']: u.get('name', 'Unknown Driver') for u in users}
    }

def get_safety_ranking(api, limit=5, group_by='device', category=None):
    """
    Get safety ranking grouped by device or driver.
    
    Args:
        limit (int): Number of results to return.
        group_by (str): 'device' or 'driver'.
        category (str): Optional filter. 'safety' (Driver Behavior) or 'health' (Vehicle Faults).
    """
    print(f"[SafetyService] get_safety_ranking called with limit={limit}, group_by={group_by}, category={category}")
    try:
        limit = int(limit)
        events = _fetch_fleet_events(api)
        print(f"[SafetyService] Fetched {len(events)} events")
        if not events:
            return []
            
        # DEBUG: Print first event structure
        if events:
            print(f"[SafetyService] Sample Event: {events[0]}")

        maps = _resolve_names(api, events)
        
        grouped_data = {} # key -> { total, breakdown, etc }
        
        for e in events:
            if not e.get('rule'): continue
            rule_id = _get_id(e['rule'])
            
            # --- Category Filtering ---
            if category == 'safety':
                if rule_id not in DRIVER_RULES: continue
            elif category == 'health':
                if rule_id not in VEHICLE_RULES: continue
            # --------------------------

            # 1. Determine Key (Driver or Device)
            if group_by == 'driver':
                # Try 'driver' first, then 'user'
                user_obj = e.get('driver') or e.get('user')
                if not user_obj:
                    # Fallback: Try to use Device name if Driver is unknown but Device is known
                    if e.get('device'):
                        dev_id = _get_id(e['device'])
                        dev_name = maps['devices'].get(dev_id, 'Unknown Device')
                        key_id = f"Device_{dev_id}"
                        key_name = f"{dev_name} (No Driver)"
                    else:
                        key_id = 'UnknownDriver'
                        key_name = 'Unknown Driver'
                else:
                    key_id = _get_id(user_obj)
                    # Skip 'System' user often used for device-level events
                    if key_id == 'NoDeviceId': 
                        continue
                    key_name = maps['users'].get(key_id, 'Unknown Driver')
            else:
                if not e.get('device'): continue
                key_id = _get_id(e['device'])
                key_name = maps['devices'].get(key_id, 'Unknown Device')
                
            # 2. Initialize bucket
            if key_id not in grouped_data:
                grouped_data[key_id] = {
                    'id': key_id,
                    'name': key_name,
                    'total_events': 0,
                    'breakdown': Counter(),
                    'categories': {'driver': 0, 'vehicle': 0}
                }
                
            # 3. Aggregate
            stats = grouped_data[key_id]
            stats['total_events'] += 1
            
            rule_name = maps['rules'].get(rule_id, rule_id)
            stats['breakdown'][rule_name] += 1
            
            # Category Count
            if rule_id in DRIVER_RULES:
                stats['categories']['driver'] += 1
            elif rule_id in VEHICLE_RULES:
                stats['categories']['vehicle'] += 1
            # Else unknown category
            
        # 4. Sort and Limit
        result = list(grouped_data.values())
        result.sort(key=lambda x: x['total_events'], reverse=True)
        
        print(f"[SafetyService] Returning {len(result[:limit])} rankings")
        return result[:limit]
        
    except Exception as e:
        print(f"[SafetyService] Ranking Error: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_driver_leaderboard(api, violation_type, limit=5):
    """
    Get ranking for a specific violation type (fuzzy match on rule name).
    """
    try:
        limit = int(limit)
        events = _fetch_fleet_events(api)
        if not events:
            return []
            
        maps = _resolve_names(api, events)
        
        grouped_data = {}
        
        violation_type_lower = violation_type.lower()
        
        for e in events:
            if not e.get('rule'): continue
            rule_id = _get_id(e['rule'])
            rule_name = maps['rules'].get(rule_id, rule_id)
            
            # Filter by violation type
            if violation_type_lower not in rule_name.lower():
                continue
                
            # Group by Driver
            user_obj = e.get('driver') or e.get('user')
            if not user_obj:
                continue
                
            key_id = _get_id(user_obj)
            key_name = maps['users'].get(key_id, 'Unknown Driver')
            
            if key_id not in grouped_data:
                grouped_data[key_id] = {
                    'id': key_id,
                    'name': key_name,
                    'count': 0,
                    'violation': rule_name # Keep one for reference
                }
            
            grouped_data[key_id]['count'] += 1
            
        result = list(grouped_data.values())
        result.sort(key=lambda x: x['count'], reverse=True)
        
        return result[:limit]
        
    except Exception as e:
        print(f"[SafetyService] Leaderboard Error: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_violation_hotspots(api, rule_name_filter=None, limit=5, device_id=None):
    """
    Find spatial hotspots for violations.
    """
    print(f"[SafetyService] get_violation_hotspots called with filter={rule_name_filter}, device_id={device_id}")
    try:
        # 1. Fetch Events
        # If device_id is provided, we can optimize the search
        search_params = {
            'fromDate': datetime.now(timezone.utc) - timedelta(days=7),
            'toDate': datetime.now(timezone.utc)
        }
        if device_id:
            search_params['deviceSearch'] = {'id': device_id}
            
        events = api.get('ExceptionEvent', search=search_params)
        if not events: return []
        
        # 2. Filter
        maps = _resolve_names(api, events)
        target_events = []
        
        for e in events:
            if not e.get('rule'): continue
            rule_id = _get_id(e['rule'])
            rule_name = maps['rules'].get(rule_id, '')
            
            if rule_name_filter and rule_name_filter.lower() not in rule_name.lower():
                continue
            
            # Double check device_id if provided (though API search should handle it)
            if device_id:
                e_device_id = _get_id(e.get('device'))
                if e_device_id != device_id:
                    continue
                    
            target_events.append(e)
            
        # 3. Get Locations (Batch/Multicall would be better, but doing simple loop for now)
        # Limit to top 50 newest to avoid timeouts
        target_events.sort(key=lambda x: x['activeFrom'], reverse=True)
        sample_events = target_events[:50]
        
        hotspots = Counter()
        
        print(f"[SafetyService] Resolving locations for {len(sample_events)} events...")
        
        for e in sample_events:
            # Try to get lat/lon if existing
            lat, lon = 0, 0
            
            # Strategy: Search LogRecord around event time
            if isinstance(e['activeFrom'], str):
                dt = datetime.fromisoformat(e['activeFrom'].replace('Z', '+00:00'))
            else:
                dt = e['activeFrom']
            
            # Widen search window to +/- 120 seconds (2 mins)
            search_window = 120
            
            if not e.get('device'): continue
            device_id = _get_id(e['device'])
            
            logs = api.get('LogRecord', search={
                'deviceSearch': {'id': device_id},
                'fromDate': dt - timedelta(seconds=search_window),
                'toDate': dt + timedelta(seconds=search_window)
            }, resultsLimit=1)
            
            # Fallback if no logs found in window
            if not logs:
                 print(f"[SafetyService] No logs in +/- {search_window}s for {device_id}, trying fallback...")
                 # Try finding the last known log before the event (up to 1 hour back)
                 logs = api.get('LogRecord', search={
                    'deviceSearch': {'id': device_id},
                    'fromDate': dt - timedelta(hours=1),
                    'toDate': dt
                }, resultsLimit=1)
            
            if logs:
                lat = logs[0]['latitude']
                lon = logs[0]['longitude']
                
            if lat != 0 and lon != 0:
                # Round to ~100m (3 decimal places)
                key = (round(lat, 3), round(lon, 3))
                hotspots[key] += 1
                
        # 4. Format Result
        result = []
        for (lat, lon), count in hotspots.most_common(limit):
            result.append({
                'latitude': lat,
                'longitude': lon,
                'count': count,
                'label': f"{lat}, {lon}" # Reverse geocoding could go here
            })
            
        return result
        
    except Exception as e:
        print(f"[SafetyService] Hotspot Error: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_fleet_safety_stats(api: mygeotab.API, days: int = 7) -> List[dict]:
    """
    Compute safety stats for the fleet based on exception events.
    Returns the top 10 vehicles with the most events.
    Args:
        days: Timeframe in days (1, 7, 30).
    """
    now = datetime.now(timezone.utc)
    from_date = now - timedelta(days=days)
    
    # 1. Fetch Exception Events for ALL vehicles
    # Using 'Get' for ExceptionEvent can be heavy, so we limit by date.
    events = api.get("ExceptionEvent", search={
        "fromDate": from_date,
        "toDate": now
    })
    
    # Group by device
    grouped_data = {}
    
    # Pre-fetch maps
    maps = _resolve_names(api, events)
    
    for e in events:
        if not e.get('rule'): continue
        rule_id = _get_id(e['rule'])
        
        # Determine Key (Device)
        if not e.get('device'): continue
        key_id = _get_id(e['device'])
        key_name = maps['devices'].get(key_id, 'Unknown Device')
        
        # Initialize bucket
        if key_id not in grouped_data:
            grouped_data[key_id] = {
                'id': key_id,
                'name': key_name,
                'total_events': 0,
                'breakdown': Counter(),
                'categories': {'driver': 0, 'vehicle': 0}
            }
            
        # Aggregate
        stats = grouped_data[key_id]
        stats['total_events'] += 1
        
        rule_name = maps['rules'].get(rule_id, rule_id)
        stats['breakdown'][rule_name] += 1
        
        # Category Count
        if rule_id in DRIVER_RULES:
            stats['categories']['driver'] += 1
        elif rule_id in VEHICLE_RULES:
            stats['categories']['vehicle'] += 1
            
    # Sort and Limit
    result = list(grouped_data.values())
    result.sort(key=lambda x: x['total_events'], reverse=True)
    
    return result

def get_vehicle_risk_events_with_location(api, device_id):
    """
    Fetch specific driver risk events for a vehicle (last 7 days)
    and enrich them with location data (Lat/Lon) for AI context.
    """
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=7)
    
    try:
        # 1. Get Driver Risk Events
        # We need to fetch rules to get names
        rules = api.get('Rule')
        rule_map = {r['id']: r.get('name', r['id']) for r in rules}

        events = api.get('ExceptionEvent', search={
            'deviceSearch': {'id': device_id},
            'fromDate': start_date,
            'toDate': end_date
        })
        
        # Filter for Driver Rules only
        risk_events = [e for e in events if e['rule']['id'] in DRIVER_RULES]
        
        # Sort by date (newest first) and take top 5
        risk_events.sort(key=lambda x: x['activeFrom'], reverse=True)
        top_events = risk_events[:5]
        
        enriched_data = []
        
        for e in top_events:
            rule_id = e['rule']['id']
            rule_name = rule_map.get(rule_id, f'Rule {rule_id}')
            event_time = e['activeFrom'] 
            
            if isinstance(event_time, str):
                dt = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
            else:
                dt = event_time
            
            search_start = dt - timedelta(seconds=30)
            search_end = dt + timedelta(seconds=30)
            
            logs = api.get('LogRecord', search={
                'deviceSearch': {'id': device_id},
                'fromDate': search_start,
                'toDate': search_end
            }, resultsLimit=1)
            
            lat, lon = 0, 0
            if logs:
                lat = logs[0]['latitude']
                lon = logs[0]['longitude']
                
            if lat != 0 or lon != 0:
                enriched_data.append({
                    'rule_name': rule_name,
                    'time': event_time,
                    'latitude': lat,
                    'longitude': lon
                })
                
        return enriched_data
        
    except Exception as e:
        print(f"[SafetyService] Error fetching details: {e}")
        return []
