
import mygeotab
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

class VehicleDetailService:
    def get_vehicle_details(self, api: mygeotab.API, device_id: str, days: int = 1) -> Dict[str, Any]:
        """
        Get detailed data for a specific vehicle:
        1. Basic Info (Device)
        2. Speed Profile (LogRecord)
        3. Fuel Level & Usage (StatusData)
        4. Utilization / Driver (DriverChange)
        5. FillUps (FillUp)
        """
        now = datetime.now(timezone.utc)
        from_date = now - timedelta(days=days)
        
        # 1. Basic Info (Device)
        # Fix: Search Device by id correctly. API 'Get' returns list.
        devices = api.get("Device", search={"id": device_id})
        if not devices:
            # If not found, return basic error dict
            return {"error": "Device not found"}
        device = devices[0]
        
        # 2. Speed Profile (LogRecord)
        # Search LogRecord for this device.
        # Note: LogRecord search uses 'deviceSearch', not 'device' directly in some versions, 
        # but typically search={'deviceSearch': {'id': ...}}
        logs = api.get("LogRecord", search={
            "deviceSearch": {"id": device_id},
            "fromDate": from_date,
            "toDate": now
        }, resultsLimit=500)
        
        speed_profile = []
        for log in logs:
            # LogRecord usually has 'speed' (km/h)
            if 'speed' in log:
                speed_profile.append({
                    "time": log['dateTime'], # Keep as datetime object or string? JSON serialization handles it usually.
                    "speed": log['speed'],
                    "lat": log['latitude'],
                    "lon": log['longitude']
                })
        
        # 3. Fuel Level (DiagnosticFuelLevelId)
        # DiagnosticFuelLevelId is widely supported.
        fuel_levels = api.get("StatusData", search={
            "deviceSearch": {"id": device_id},
            "diagnosticSearch": {"id": "DiagnosticFuelLevelId"},
            "fromDate": from_date,
            "toDate": now
        }, resultsLimit=100)
        
        fuel_data = []
        for f in fuel_levels:
            fuel_data.append({
                "time": f['dateTime'],
                "level": f['data']
            })

        # 4. Total Fuel Used (Snapshot)
        total_fuel = None
        # Try to get the latest Total Fuel reading
        tf_records = api.get("StatusData", search={
            "deviceSearch": {"id": device_id},
            "diagnosticSearch": {"id": "DiagnosticDeviceTotalFuelId"},
            "fromDate": from_date,
            "toDate": now
        }, resultsLimit=1)
        if tf_records:
            total_fuel = tf_records[0]['data']

        # 5. Driver Changes
        driver_changes = api.get("DriverChange", search={
            "deviceSearch": {"id": device_id},
            "fromDate": from_date,
            "toDate": now
        }, resultsLimit=10)
        
        drivers = []
        for dc in driver_changes:
            # Handle Driver object safely
            driver_obj = dc.get('driver', {})
            d_name = "Unknown"
            if isinstance(driver_obj, dict):
                d_name = driver_obj.get('name', 'Unknown')
            elif hasattr(driver_obj, 'name'):
                d_name = driver_obj.name
            else:
                d_name = str(driver_obj)
                
            drivers.append({
                "time": dc['dateTime'],
                "driver": d_name,
                "type": dc.get('type')
            })

        # 6. FillUps
        fillups = api.get("FillUp", search={
            "deviceSearch": {"id": device_id},
            "fromDate": from_date,
            "toDate": now
        }, resultsLimit=5)
        
        fillup_events = []
        for fu in fillups:
            fillup_events.append({
                "time": fu['dateTime'],
                "volume": fu.get('fuelVolume'),
                "odometer": fu.get('odometer'),
                "price": fu.get('price')
            })

        return {
            "device": {
                "id": device['id'],
                "name": device['name'],
                "vin": device.get('vehicleIdentificationNumber'),
                "licensePlate": device.get('licensePlate')
            },
            "speed_profile": speed_profile,
            "fuel": {
                "level_history": fuel_data,
                "total_used": total_fuel,
                "fillups": fillup_events
            },
            "drivers": drivers
        }

vehicle_detail_service = VehicleDetailService()
