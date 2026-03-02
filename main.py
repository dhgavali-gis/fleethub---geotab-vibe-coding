
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os
import json
import asyncio

from services.auth_service import geotab_client
from services.geotab_service import (
    get_all_devices, 
    get_device_status_info, 
    get_log_records, 
    find_nearest_history,
    get_exception_events,
    enrich_events_with_location
)
from services.safety_service import get_fleet_safety_stats
from services.ace_service import ace_service
from services.traffic_service import traffic_service
from services.mcp_service import mcp_service
from services.dashboard_service import dashboard_service
from services.vehicle_detail_service import vehicle_detail_service

app = FastAPI(title="Fleet Intelligence Hub API")

# Mount static files (Frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Data Models ---
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    map_command: Optional[dict] = None # Deprecated
    map_commands: Optional[List[dict]] = None # New standard
    thinking_process: Optional[List[dict]] = None # New thinking process logs

class DeviceStatus(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    speed: float
    isDriving: bool
    dateTime: datetime | str

class LogRecord(BaseModel):
    latitude: float
    longitude: float
    speed: float
    dateTime: datetime | str  # Allow both datetime object and string

class VehicleEvent(BaseModel):
    time: datetime | str
    ruleName: str
    duration: str
    latitude: float
    longitude: float

class HistoryResponse(BaseModel):
    logs: List[LogRecord]
    events: List[VehicleEvent] = []
    actualDate: Optional[str] = None
    message: Optional[str] = None

class SafetyStat(BaseModel):
    id: str
    name: str
    total_events: int
    breakdown: dict
    categories: dict  # Added categories

class IncidentCheckRequest(BaseModel):
    latitude: float
    longitude: float

class Incident(BaseModel):
    category: int | None
    description: str | None
    magnitude: int | None
    coordinates: List | None

# --- Routes ---

@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

@app.get("/@vite/client")
async def vite_client_placeholder():
    """Placeholder to silence 404 errors from browsers expecting Vite dev server."""
    return ""

@app.get("/api/config/tomtom-key")
async def get_tomtom_key():
    """Get TomTom API Key for frontend (Development only)."""
    return {"key": traffic_service.api_key}

@app.post("/api/traffic/check-incidents", response_model=List[Incident])
async def check_incidents(req: IncidentCheckRequest):
    """Check for traffic incidents around a specific location."""
    return traffic_service.check_nearby_incidents(req.latitude, req.longitude)


@app.get("/api/vehicles", response_model=List[DeviceStatus])
async def get_vehicles():
    """Get real-time locations of all vehicles."""
    api = geotab_client.get_api()
    if not api:
        raise HTTPException(status_code=503, detail="Geotab API unavailable")
    
    # In a production app, you'd cache the device list
    devices = get_all_devices(api)
    status_info = get_device_status_info(api, devices)
    return status_info

@app.get("/api/history/{device_id}", response_model=HistoryResponse)
async def get_history(device_id: str, date: str):
    """
    Get historical path for a vehicle. 
    Auto-backtracks up to 30 days if no data found on selected date.
    """
    api = geotab_client.get_api()
    if not api:
        raise HTTPException(status_code=503, detail="Geotab API unavailable")

    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
        
        # Use smart search
        logs, actual_date = find_nearest_history(api, device_id, target_date)
        
        if not logs:
            return HistoryResponse(logs=[], events=[], message="No history found in the last 30 days")
            
        # 1. Determine date range for events based on actual_date
        event_date = datetime.strptime(actual_date, "%Y-%m-%d")
        start_dt = event_date.replace(hour=0, minute=0, second=0)
        end_dt = event_date.replace(hour=23, minute=59, second=59)
        
        # 2. Fetch raw events
        raw_events = get_exception_events(api, device_id, start_dt, end_dt)
        
        # 3. Enrich with location
        events = enrich_events_with_location(raw_events, logs)
        
        message = None
        if actual_date != date:
            message = f"No data on {date}. Showing nearest data from {actual_date}"
            
        return HistoryResponse(logs=logs, events=events, actualDate=actual_date, message=message)
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

@app.get("/api/devices")
async def get_devices_list():
    """Get simple list of devices for dropdown."""
    api = geotab_client.get_api()
    if not api:
        raise HTTPException(status_code=503, detail="Geotab API unavailable")
    
    devices = get_all_devices(api)
    return [{"id": d['id'], "name": d['name']} for d in devices]

@app.get("/api/vehicle/{device_id}/details")
async def get_vehicle_details(device_id: str, days: int = 1):
    """
    Get detailed vehicle stats (Speed, Fuel, Utilization).
    """
    api = geotab_client.get_api()
    if not api:
        raise HTTPException(status_code=503, detail="Geotab API unavailable")
    
    try:
        details = await asyncio.to_thread(
            vehicle_detail_service.get_vehicle_details, 
            api, 
            device_id, 
            days
        )
        return details
    except Exception as e:
        print(f"Error fetching vehicle details: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard/stats")
async def get_dashboard_stats(days: int = 7):
    """
    Get aggregated stats for the dashboard.
    Args:
        days: Timeframe in days (1, 7, 30). Default is 7.
    """
    return dashboard_service.get_kpi_stats(days=days)

@app.get("/api/coach/ranking", response_model=List[SafetyStat])
async def get_safety_ranking(days: int = 7):
    """
    Get fleet safety ranking (Top 10 worst).
    Args:
        days: Timeframe in days (1, 7, 30). Default is 7.
    """
    api = geotab_client.get_api()
    if not api:
        raise HTTPException(status_code=503, detail="Geotab API unavailable")
        
    return get_fleet_safety_stats(api, days=days)

@app.post("/api/coach/generate/{device_id}")
async def generate_advice(device_id: str, stats: dict):
    """
    Trigger AI advice generation.
    Note: In production, this should be a background task (Celery/Redis).
    Here we await it (Wait-and-Poll is handled in service), which might take 30-60s.
    """
    api = geotab_client.get_api()
    if not api:
        raise HTTPException(status_code=503, detail="Geotab API unavailable")
        
    # Get device name for prompt
    devices = get_all_devices(api)
    device_name = next((d['name'] for d in devices if d['id'] == device_id), "Unknown Vehicle")
    
    result = await ace_service.generate_coaching_advice(api, device_id, device_name, stats)
    return {"advice": result}

@app.post("/api/mcp/chat", response_model=ChatResponse)
async def mcp_chat(req: ChatRequest):
    """
    MCP Mode Chat Endpoint.
    Uses Gemini + Tools to answer complex fleet questions.
    """
    result = await mcp_service.chat(req.message)
    return ChatResponse(
        response=result.get("response", ""),
        map_commands=result.get("map_commands"),
        thinking_process=result.get("thinking_process")
    )

@app.post("/api/mcp/chat/stream")
async def mcp_chat_stream(req: ChatRequest):
    """
    Streamed MCP Chat.
    Yields 'tool_call', 'tool_result', and finally 'result' events.
    """
    async def event_generator():
        queue = asyncio.Queue()
        
        def on_log(log_entry):
            queue.put_nowait(log_entry)
            
        task = asyncio.create_task(mcp_service.chat(req.message, on_log=on_log))
        
        # Loop until task is done
        while not task.done():
            try:
                # Wait for new item in queue with timeout to check task status
                # If we just await queue.get(), we might hang if task finishes without adding more items
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    continue
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
                break
        
        # Flush remaining items
        while not queue.empty():
            msg = await queue.get()
            yield f"data: {json.dumps(msg)}\n\n"
            
        # Get final result
        try:
            result = await task
            final_data = {
                "type": "result",
                "response": result.get("response", ""),
                "map_commands": result.get("map_commands"),
                # We can also include the full thinking_process for history, but we streamed it.
            }
            yield f"data: {json.dumps(final_data)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/mcp/reset")
async def mcp_reset():
    """Reset the MCP chat session history."""
    mcp_service._init_model(mcp_service.current_model_name)
    return {"status": "success", "message": "Chat session reset."}
