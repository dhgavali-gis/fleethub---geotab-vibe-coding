
import os
import mygeotab
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

DATABASE = os.getenv("GEOTAB_DATABASE")
USERNAME = os.getenv("GEOTAB_USERNAME")
PASSWORD = os.getenv("GEOTAB_PASSWORD")
SERVER = os.getenv("GEOTAB_SERVER")

if not all([DATABASE, USERNAME, PASSWORD, SERVER]):
    print("Error: Missing credentials in .env file.")
    exit(1)

def authenticate():
    try:
        api = mygeotab.API(username=USERNAME, password=PASSWORD, database=DATABASE, server=SERVER)
        api.authenticate()
        print(f"Successfully authenticated to {DATABASE}")
        return api
    except Exception as e:
        print(f"Authentication failed: {e}")
        return None

def test_speed_profile(api):
    print("\n--- Testing 1. Speed Profile (LogRecord & StatusData) ---")
    try:
        # Get last 10 LogRecords (GPS Breadcrumbs)
        logs = api.get("LogRecord", resultsLimit=10)
        print(f"LogRecord (GPS Breadcrumbs): Found {len(logs)} records.")
        if logs:
            print(f"Sample LogRecord Speed: {logs[0].get('speed', 'N/A')} km/h at {logs[0].get('dateTime')}")

        # Get DiagnosticEngineRoadSpeedId (StatusData)
        # Note: Need a valid device/diagnostic/fromDate to search efficiently, but limited search is okay for test.
        # We'll search for 'DiagnosticEngineRoadSpeedId' specifically.
        
        # Searching StatusData without device/date can be slow/heavy. Let's limit date to last 24h.
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        
        status_data = api.get("StatusData", search={
            "diagnosticSearch": {"id": "DiagnosticEngineRoadSpeedId"},
            "fromDate": yesterday,
            "toDate": now
        }, resultsLimit=5)
        
        print(f"StatusData (Engine Speed): Found {len(status_data)} records.")
        if status_data:
            print(f"Sample Engine Speed: {status_data[0].get('data', 'N/A')} km/h")
        else:
            print("No Engine Speed data found in last 24h (DiagnosticEngineRoadSpeedId). trying GPS Speed (DiagnosticSpeedId)")
            status_data_gps = api.get("StatusData", search={
                "diagnosticSearch": {"id": "DiagnosticSpeedId"},
                "fromDate": yesterday,
                "toDate": now
            }, resultsLimit=5)
            print(f"StatusData (GPS Speed): Found {len(status_data_gps)} records.")
            if status_data_gps:
                print(f"Sample GPS Speed: {status_data_gps[0].get('data', 'N/A')} km/h")

    except Exception as e:
        print(f"Error testing Speed Profile: {e}")

def test_time_card(api):
    print("\n--- Testing 2. Time Card Report (DutyStatusLog & DriverChange) ---")
    try:
        # DutyStatusLog (HOS/ELD)
        duty_logs = api.get("DutyStatusLog", resultsLimit=5)
        print(f"DutyStatusLog (HOS/ELD): Found {len(duty_logs)} records.")
        if duty_logs:
            print(f"Sample Duty Status: {duty_logs[0].get('status')} at {duty_logs[0].get('dateTime')}")
        else:
            print("No DutyStatusLog found (HOS might not be enabled or used).")

        # DriverChange
        driver_changes = api.get("DriverChange", resultsLimit=5)
        print(f"DriverChange: Found {len(driver_changes)} records.")
        if driver_changes:
            # DriverChange object structure: {'dateTime': ..., 'driver': {'id': '...', 'name': '...'}, 'device': {'id': '...'}}
            # Or it might be simpler in some SDK versions. Let's inspect it safely.
            dc = driver_changes[0]
            print(f"Sample Driver Change Record: {dc}")
            
            driver_info = dc.get('driver', {})
            if isinstance(driver_info, dict):
                driver_id = driver_info.get('id', 'Unknown')
            else:
                driver_id = str(driver_info)
                
            print(f"Sample Driver Change: Driver {driver_id} at {dc.get('dateTime')}")

    except Exception as e:
        print(f"Error testing Time Card: {e}")

def test_fuel_energy(api):
    print("\n--- Testing 3. Fuel & Energy Usage (FuelUsed & StatusData) ---")
    try:
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        # StatusData: Fuel Level (DiagnosticFuelLevelId)
        fuel_level = api.get("StatusData", search={
            "diagnosticSearch": {"id": "DiagnosticFuelLevelId"}, # Percentage
            "fromDate": week_ago,
            "toDate": now
        }, resultsLimit=5)
        print(f"StatusData (Fuel Level %): Found {len(fuel_level)} records.")
        if fuel_level:
            print(f"Sample Fuel Level: {fuel_level[0].get('data')}%")

        # StatusData: Total Fuel Used (DiagnosticDeviceTotalFuelId)
        total_fuel = api.get("StatusData", search={
            "diagnosticSearch": {"id": "DiagnosticDeviceTotalFuelId"}, # Liters
            "fromDate": week_ago,
            "toDate": now
        }, resultsLimit=5)
        print(f"StatusData (Total Fuel Used): Found {len(total_fuel)} records.")
        if total_fuel:
            print(f"Sample Total Fuel: {total_fuel[0].get('data')} L")

        # FuelUsed (Calculated entity) - Note: This might require specific engine data
        # 'FuelUsed' entity is not always directly available via Get, usually calculated.
        # But 'StatusData' for 'DiagnosticFuelUsedId' exists.
        # Let's check for 'FuelTransaction' here as well? No, that's next section.
        # Let's check for specific diagnostics related to fuel usage.
        
        # 'Trip' objects often have fuel usage if processed.
        trips = api.get("Trip", search={"fromDate": week_ago, "toDate": now}, resultsLimit=5)
        if trips:
            # Check if Trip object has fuel info (might need to check if it's populated)
            # Trip object usually has: afterHoursDistance, distance, drivingDuration, stopDuration... 
            # Fuel might be in engine hours or auxiliary.
            # Actually, standard Trip object doesn't have fuelUsed field directly, it's often calculated from StatusData.
            pass

    except Exception as e:
        print(f"Error testing Fuel & Energy: {e}")

def test_fillups(api):
    print("\n--- Testing 4. Detected Fillups (FillUp & FuelTransaction) ---")
    try:
        now = datetime.now(timezone.utc)
        month_ago = now - timedelta(days=30) # Fillups are less frequent

        # FillUp (Detected events)
        fillups = api.get("FillUp", search={"fromDate": month_ago, "toDate": now}, resultsLimit=5)
        print(f"FillUp (Detected Events): Found {len(fillups)} records.")
        if fillups:
            print(f"Sample FillUp: {fillups[0].get('fuelVolume')} L at {fillups[0].get('dateTime')}")

        # FuelTransaction (Fuel Card integration)
        transactions = api.get("FuelTransaction", search={"fromDate": month_ago, "toDate": now}, resultsLimit=5)
        print(f"FuelTransaction (Card Records): Found {len(transactions)} records.")
        if transactions:
            print(f"Sample Transaction: {transactions[0].get('volume')} L at {transactions[0].get('dateTime')}")

    except Exception as e:
        print(f"Error testing Fillups: {e}")

if __name__ == "__main__":
    api = authenticate()
    if api:
        test_speed_profile(api)
        test_time_card(api)
        test_fuel_energy(api)
        test_fillups(api)
