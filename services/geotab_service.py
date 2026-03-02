
from datetime import datetime, timedelta
from mygeotab.exceptions import MyGeotabException
import pandas as pd
from math import radians, cos, sin, asin, sqrt

def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees) in km.
    """
    # convert decimal degrees to radians 
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # haversine formula 
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    r = 6371 # Radius of earth in kilometers. Use 3956 for miles
    return c * r

def clean_trajectory(logs):
    """
    Filter out GPS points that imply impossible speeds (> 250 km/h)
    or unreasonable jumps.
    """
    if not logs:
        return []
        
    cleaned_logs = []
    if len(logs) > 0:
        cleaned_logs.append(logs[0]) # Keep first point
        
    for i in range(1, len(logs)):
        prev = cleaned_logs[-1] # Compare with last valid point
        curr = logs[i]
        
        # Calculate distance (km)
        dist = haversine(prev['longitude'], prev['latitude'], 
                        curr['longitude'], curr['latitude'])
        
        # Calculate time delta (hours)
        # Ensure dateTime is datetime object
        t1 = prev['dateTime']
        t2 = curr['dateTime']
        
        # If string, parse it (robustness)
        if isinstance(t1, str): t1 = datetime.fromisoformat(t1.replace('Z', '+00:00'))
        if isinstance(t2, str): t2 = datetime.fromisoformat(t2.replace('Z', '+00:00'))
            
        time_diff = (t2 - t1).total_seconds() / 3600.0 # hours
        
        if time_diff <= 0:
            # Duplicate timestamp or out of order? Skip or keep?
            # If distance is small, maybe keep. If large, skip.
            if dist > 0.1: # 100 meters jump in 0 seconds = impossible
                continue
            else:
                cleaned_logs.append(curr)
                continue
                
        speed = dist / time_diff # km/h
        
        # Threshold: 250 km/h (allowing for some GPS noise, but filtering trans-oceanic jumps)
        if speed > 250:
            # print(f"[DEBUG] Filtered jump: {dist:.2f}km in {time_diff*3600:.1f}s = {speed:.0f} km/h")
            continue
            
        cleaned_logs.append(curr)
        
    return cleaned_logs


# Cache for devices to reduce API load
_device_cache = {
    'data': [],
    'last_updated': datetime.min
}

def get_all_devices(api):
    """Fetch all devices from the fleet with caching."""
    global _device_cache
    
    # Check cache (valid for 5 minutes)
    if (datetime.now() - _device_cache['last_updated']).total_seconds() < 300 and _device_cache['data']:
        # print("[DEBUG] Using cached device list")
        return _device_cache['data']

    try:
        # Get active devices only (optional, but good for performance)
        devices = api.get('Device')
        print(f"[DEBUG] Fetched {len(devices)} devices (API Call)")
        
        # Log first device to check structure
        if devices:
            print(f"[DEBUG] First device sample: {devices[0].get('name')} (ID: {devices[0].get('id')})")
        
        # Update cache
        _device_cache['data'] = devices
        _device_cache['last_updated'] = datetime.now()
            
        return devices
    except MyGeotabException as e:
        print(f"Error fetching devices: {e}")
        return []

# Cache for status to prevent request flooding
_status_cache = {
    'data': [],
    'last_updated': datetime.min
}

def get_device_status_info(api, devices=None):
    """
    Fetch real-time status info for devices with micro-caching (1 second).
    """
    global _status_cache
    
    # Micro-cache: Return cached data if request is within 1 second
    # This prevents API flooding from multiple clients or rapid polling
    if (datetime.now() - _status_cache['last_updated']).total_seconds() < 1 and _status_cache['data']:
        # print("[DEBUG] Using micro-cached status")
        return _status_cache['data']

    try:
        # deviceStatusInfo contains lat, lon, speed, isDriving, etc.
        status_info = api.get('DeviceStatusInfo')
        print(f"[DEBUG] Fetched {len(status_info)} status info records")
        
        # Create a lookup for device names if devices list is provided
        device_map = {d['id']: d['name'] for d in devices} if devices else {}
        
        enriched_data = []
        skipped_count = 0
        
        for info in status_info:
            device_id = info['device']['id']
            # Only include if we have the device in our list (if provided)
            if devices and device_id not in device_map:
                continue
                
            name = device_map.get(device_id, 'Unknown Device')
            
            # Basic validation for coordinates
            lat = info.get('latitude', 0)
            lon = info.get('longitude', 0)
            
            # If lat/lon is 0, try to fetch the latest LogRecord as a fallback
            if lat == 0 and lon == 0:
                try:
                    # Fetch just the last 1 log record from the last 24 hours
                    logs = api.get('LogRecord', search={
                        'deviceSearch': {'id': device_id},
                        'fromDate': datetime.utcnow() - timedelta(days=1),
                        'toDate': datetime.utcnow()
                    }, resultsLimit=1)
                    
                    if logs and len(logs) > 0:
                        lat = logs[0]['latitude']
                        lon = logs[0]['longitude']
                        # print(f"[DEBUG] Device {name} used fallback LogRecord: {lat}, {lon}")
                    else:
                        skipped_count += 1
                        # If still no location, we can't show it on map
                        # continue 
                except Exception as e:
                    print(f"[DEBUG] Fallback LogRecord failed for {name}: {e}")
                    skipped_count += 1
            
            # Final check - if we have valid coords (either from status or fallback)
            if lat != 0 or lon != 0:
                enriched_data.append({
                    'id': device_id,
                    'name': name,
                    'latitude': lat,
                    'longitude': lon,
                    'speed': info.get('speed', 0), 
                    'isDriving': info.get('isDeviceDriving', False),
                    'dateTime': info.get('dateTime', datetime.now().isoformat())
                })
            
        print(f"[DEBUG] Returning {len(enriched_data)} enriched records (Skipped {skipped_count} with 0,0 coords)")
        
        # Update cache
        _status_cache['data'] = enriched_data
        _status_cache['last_updated'] = datetime.now()
        
        return enriched_data
    except MyGeotabException as e:
        print(f"Error fetching device status: {e}")
        return []

def get_log_records(api, device_id, start_date, end_date):
    """
    Fetch historical GPS logs (LogRecord) for a specific device.
    """
    try:
        print(f"[DEBUG] Fetching logs for {device_id} from {start_date} to {end_date}")
        logs = api.get('LogRecord', search={
            'deviceSearch': {'id': device_id},
            'fromDate': start_date,
            'toDate': end_date
        })
        
        print(f"[DEBUG] Fetched {len(logs)} log records for {device_id}")
        
        if not logs:
            return []
            
        # Transform to list of dicts for JSON response
        raw_result = []
        for log in logs:
            lat = log.get('latitude', 0)
            lon = log.get('longitude', 0)
            
            # Filter out 0,0 and potential null island artifacts
            if lat == 0 and lon == 0:
                continue
                
            raw_result.append({
                'latitude': lat,
                'longitude': lon,
                'speed': log.get('speed', 0),
                'dateTime': log.get('dateTime')
            })
            
        # Apply advanced cleaning
        cleaned_result = clean_trajectory(raw_result)
        print(f"[DEBUG] Cleaned trajectory: {len(raw_result)} -> {len(cleaned_result)} points")
        
        return cleaned_result
    except MyGeotabException as e:
        print(f"Error fetching log records: {e}")
        return []

def find_nearest_history(api, device_id, target_date):
    """
    Search for history on the target date. If empty, look back up to 7 days.
    Returns: (logs, actual_date_str) or ([], None)
    """
    # 1. Try target date first
    # IMPORTANT: Ensure start/end are datetime objects, not just date
    start_dt = target_date.replace(hour=0, minute=0, second=0)
    end_dt = target_date.replace(hour=23, minute=59, second=59)
    
    logs = get_log_records(api, device_id, start_dt, end_dt)
    if logs:
        return logs, target_date.strftime("%Y-%m-%d")
    
    # 2. Look back 30 days (Increased from 7)
    print(f"[DEBUG] No logs for {target_date.date()}, looking back 30 days...")
    for i in range(1, 31):
        past_date = target_date - timedelta(days=i)
        start_dt = past_date.replace(hour=0, minute=0, second=0)
        end_dt = past_date.replace(hour=23, minute=59, second=59)
        
        # Only print debug every 5 days to reduce noise
        if i % 5 == 0:
            print(f"[DEBUG] Checking {past_date.date()}...")
            
        logs = get_log_records(api, device_id, start_dt, end_dt)
        if logs:
            print(f"[DEBUG] Found {len(logs)} logs on {past_date.date()}")
            return logs, past_date.strftime("%Y-%m-%d")
            
    return [], None

def get_exception_events(api, device_id, start_date, end_date):
    """
    Fetch ExceptionEvents (Rule Violations) for a device in a date range.
    Retries with broader scope if no events found initially.
    """
    try:
        print(f"[DEBUG] Fetching exception events for {device_id} from {start_date} to {end_date}")
        events = api.get('ExceptionEvent', search={
            'deviceSearch': {'id': device_id},
            'fromDate': start_date,
            'toDate': end_date
        })
        
        # Retry Strategy: If no events, try expanding the window by +/- 12 hours
        # Sometimes events happen just outside the driving log window
        if not events:
            print(f"[DEBUG] No events found in exact window. Expanding search...")
            expanded_start = start_date - timedelta(hours=12)
            expanded_end = end_date + timedelta(hours=12)
            events = api.get('ExceptionEvent', search={
                'deviceSearch': {'id': device_id},
                'fromDate': expanded_start,
                'toDate': expanded_end
            })
            if events:
                print(f"[DEBUG] Found {len(events)} events in expanded window!")
        
        if not events:
            return []
            
        # Get Rule names
        try:
            rules = api.get('Rule')
            rule_map = {r['id']: r['name'] for r in rules}
        except:
            rule_map = {}
            
        enriched_events = []
        for e in events:
            rule_id = e['rule']['id']
            
            # Format duration
            duration = str(e.get('duration', '00:00:00'))
            
            enriched_events.append({
                'time': e['activeFrom'],
                'ruleName': rule_map.get(rule_id, f'Rule {rule_id}'),
                'duration': duration,
                # Placeholders for location
                'latitude': 0,
                'longitude': 0
            })
            
        print(f"[DEBUG] Fetched {len(enriched_events)} events")
        return enriched_events
    except MyGeotabException as e:
        print(f"Error fetching events: {e}")
        return []

def enrich_events_with_location(events, logs):
    """
    Attach latitude/longitude to events by finding the closest LogRecord.
    """
    if not events or not logs:
        return events
        
    # Helper to parse time
    def parse_time(t):
        if isinstance(t, str):
            return datetime.fromisoformat(t.replace('Z', '+00:00'))
        return t

    # Pre-parse log times for speed
    log_times = []
    for log in logs:
        log_times.append({
            'time': parse_time(log['dateTime']),
            'lat': log['latitude'],
            'lon': log['longitude']
        })
        
    for event in events:
        event_time = parse_time(event['time'])
        
        best_match = None
        min_diff = 300 # 5 minutes threshold
        
        for log in log_times:
            diff = abs((log['time'] - event_time).total_seconds())
            if diff < min_diff:
                min_diff = diff
                best_match = log
        
        if best_match:
            event['latitude'] = best_match['lat']
            event['longitude'] = best_match['lon']
            
    # Filter out events that couldn't be located (still 0,0)
    return [e for e in events if e['latitude'] != 0 or e['longitude'] != 0]
