import os
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Callable

from dotenv import load_dotenv
import mygeotab
import googlemaps

from PydanticAI.agent import agent
from PydanticAI.deps import SystemDeps
from PydanticAI.models import AgentResponse
from services.memory_manager import MemoryManager
from services.duckdb_manager import DuckDBManager
from services.traffic_service import traffic_service
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, TextPart
from pydantic_ai.exceptions import UsageLimitExceeded, UnexpectedModelBehavior

load_dotenv()

class MCPService:
    def __init__(self) -> None:
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            print("[MCPService] Warning: GOOGLE_API_KEY is missing.")
        else:
            self.gmp_client = googlemaps.Client(key=self.api_key)
        
        # Initialize Managers
        self.memory_manager = MemoryManager()
        self.duckdb_manager = DuckDBManager()
        
        # In-memory history for short-term context (per session/instance)
        # Note: In a real multi-user app, this should be keyed by session_id/user_id
        self.history = []
        
        # Preload data
        self._preload_data()
        
        print(f"[MCPService] PydanticAI Agent initialized.")

    def _get_api(self) -> mygeotab.API:
        """Helper to authenticate with Geotab using environment-based credentials."""
        username = os.getenv("GEOTAB_USERNAME")
        password = os.getenv("GEOTAB_PASSWORD")
        database = os.getenv("GEOTAB_DATABASE")
        server = os.getenv("GEOTAB_SERVER")

        api = mygeotab.API(
            username=username, password=password, database=database, server=server
        )
        api.authenticate()
        return api

    def _preload_data(self):
        """Preload initial data into DuckDB."""
        try:
            api = self._get_api()
            
            # 1. Preload Devices
            devices = api.get("Device")
            if devices:
                # Convert to DataFrame-friendly list of dicts
                device_data = []
                for d in devices:
                    device_data.append({
                        "id": d.get("id"),
                        "name": d.get("name"),
                        "serialNumber": d.get("serialNumber"),
                        "vehicleIdentificationNumber": d.get("vehicleIdentificationNumber"),
                        "deviceType": d.get("deviceType"),
                        "activeFrom": d.get("activeFrom"),
                        "activeTo": d.get("activeTo")
                    })
                
                import pandas as pd
                df_dev = pd.DataFrame(device_data)
                self.duckdb_manager.conn.register('temp_devices', df_dev)
                # Clear existing and insert
                self.duckdb_manager.conn.execute("DELETE FROM devices")
                self.duckdb_manager.conn.execute("INSERT INTO devices SELECT * FROM temp_devices")
                self.duckdb_manager.conn.unregister('temp_devices')
                print(f"[MCPService] Preloaded {len(device_data)} devices into DuckDB.")
                
                # 2. Preload Logs (Recent 7 days for top 5 active devices to match event data)
                # Find active devices (no activeTo or activeTo > now)
                now = datetime.now(timezone.utc)
                active_devices = []
                for d in devices:
                    # ... (filtering logic same as before) ...
                    active_to = d.get("activeTo")
                    is_active = False
                    if not active_to:
                        is_active = True
                    elif isinstance(active_to, datetime):
                        if active_to.tzinfo is None:
                            active_to = active_to.replace(tzinfo=timezone.utc)
                        is_active = active_to > now
                    elif isinstance(active_to, str):
                        is_active = active_to > now.isoformat()
                    
                    if is_active:
                        active_devices.append(d)

                # Sort devices to prioritize 'Demo - 18' and other violators
                # Then take top 20
                def device_sort_key(d):
                    name = d.get('name', '').lower()
                    if 'demo - 18' in name: return 0 # Top priority
                    if 'demo - 04' in name: return 1
                    if 'demo - 02' in name: return 2
                    if 'demo - 20' in name: return 3
                    return 100
                
                active_devices.sort(key=device_sort_key)
                
                top_devices = active_devices[:5] 
                
                all_logs = []
                # now is already UTC aware
                # Increase to 7 days to ensure we can map locations for all events
                from_date_logs = now - timedelta(days=7) 
                
                for d in top_devices:
                    logs = api.get("LogRecord", search={"deviceSearch": {"id": d['id']}, "fromDate": from_date_logs, "toDate": now})
                    if logs:
                        for l in logs:
                            all_logs.append({
                                "device_id": l['device']['id'],
                                "dateTime": l['dateTime'],
                                "latitude": l['latitude'],
                                "longitude": l['longitude'],
                                "speed": l['speed'],
                                "rpm": l.get('rpm', 0),
                                "volts": l.get('volts', 0)
                            })
                
                if all_logs:
                    # ... (Store logs) ...
                    df_logs = pd.DataFrame(all_logs)
                    self.duckdb_manager.conn.register('temp_logs', df_logs)
                    self.duckdb_manager.conn.execute("DELETE FROM logs")
                    self.duckdb_manager.conn.execute("INSERT INTO logs SELECT * FROM temp_logs")
                    self.duckdb_manager.conn.unregister('temp_logs')
                    print(f"[MCPService] Preloaded {len(all_logs)} logs into DuckDB (Last 7 days).")
                else:
                    print("[MCPService] No logs found to preload.")

                # 3. Preload Rules
                rules = api.get("Rule")
                if rules:
                    rule_data = []
                    for r in rules:
                         rule_data.append({
                             "id": r.get("id"),
                             "name": r.get("name"),
                             "baseType": r.get("baseType"),
                             "activeFrom": r.get("activeFrom"),
                             "activeTo": r.get("activeTo")
                         })
                    
                    df_rules = pd.DataFrame(rule_data)
                    self.duckdb_manager.conn.register('temp_rules', df_rules)
                    self.duckdb_manager.conn.execute("DELETE FROM rules")
                    self.duckdb_manager.conn.execute("INSERT INTO rules SELECT * FROM temp_rules")
                    self.duckdb_manager.conn.unregister('temp_rules')
                    print(f"[MCPService] Preloaded {len(rule_data)} rules into DuckDB.")

                # 4. Preload Exception Events (Last 7 days)
                events_from_date = now - timedelta(days=7)
                all_events = []
                for d in top_devices:
                    # Get ExceptionEvent
                    events = api.get("ExceptionEvent", search={"deviceSearch": {"id": d['id']}, "fromDate": events_from_date, "toDate": now})
                    if events:
                        for e in events:
                            # Safely extract data
                            rule = e.get('rule') or {}
                            rule_id = rule.get('id') if isinstance(rule, dict) else rule
                            
                            device = e.get('device') or {}
                            device_id = device.get('id') if isinstance(device, dict) else device
                            
                            all_events.append({
                                "id": e.get("id"),
                                "device_id": device_id,
                                "rule_id": rule_id,
                                "activeFrom": e.get("activeFrom"),
                                "activeTo": e.get("activeTo"),
                                "duration": str(e.get("duration")), # Cast duration to string
                                "latitude": None,
                                "longitude": None
                            })
                
                # Preload Logs (Increase to 7 days to match events? Or at least 48h?)
                # Let's try 48h for now to balance speed/data.
                from_date_logs = now - timedelta(days=2) 
                
                # ... (Log preloading logic updated below) ...

                if all_events:
                    df_events = pd.DataFrame(all_events)
                    self.duckdb_manager.conn.register('temp_events', df_events)
                    self.duckdb_manager.conn.execute("DELETE FROM events")
                    self.duckdb_manager.conn.execute("INSERT INTO events SELECT * FROM temp_events")
                    self.duckdb_manager.conn.unregister('temp_events')
                    print(f"[MCPService] Preloaded {len(all_events)} exception events into DuckDB.")
                else:
                    print("[MCPService] No exception events found to preload.")
                
        except Exception as e:
            print(f"[MCPService] Failed to preload data: {e}")

    async def chat(self, user_message: str, on_log: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        try:
            # Prepare Dependencies
            api = self._get_api()
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            # Inject Date into User Message to prevent hallucination
            augmented_message = f"Current Date: {current_date}\nUser Query: {user_message}"
            
            deps = SystemDeps(
                geotab_api=api,
                gmp_client=self.gmp_client,
                duckdb_manager=self.duckdb_manager,
                memory_manager=self.memory_manager,
                traffic_service=traffic_service,
                current_date=current_date,
                on_log=on_log
            )
            
            # Run Agent
            try:
                # Pass history to maintain context
                result = await agent.run(augmented_message, deps=deps, message_history=self.history)
                response_data = result.output
                # Update history with new messages (User + AI + Tool interactions)
                self.history = result.new_messages()
            except UsageLimitExceeded as e:
                # Handle iteration limit (infinite loop)
                response_data = AgentResponse(
                    final_answer="I stopped because I was thinking for too long (iteration limit reached). Please see the thinking process for details.",
                    confidence_score=0.0,
                    steps_taken=[]
                )
                # Try to recover history from exception if available, otherwise empty
                self.history = getattr(e, 'messages', []) or []
            except Exception as e:
                raise e

            # Extract Thinking Process from History
            thinking_process = []
            # We want to extract steps only from the NEW interaction, but self.history now contains EVERYTHING.
            # However, for the UI "Thinking Process", we only want the latest turn's steps.
            # result.new_messages() returns the *entire* history if passed back, OR just the new ones?
            # PydanticAI: result.new_messages() returns the list of messages that were added in this run.
            # Wait, result.new_messages() returns the updated COMPLETE history if we passed history in?
            # Let's check the docs pattern. Usually it returns the *new* messages or the *complete* list.
            # Actually, `agent.run` returns a `RunResult` which has `new_messages()`.
            # If we passed `message_history`, `new_messages()` usually returns the *complete* history including the new ones.
            # But for the UI, we only want to show the tools called *this time*.
            # We can filter `self.history` to find the messages after the last user message.
            
            # Simple approach: Iterate backwards until we hit the last User text message
            
            current_turn_messages = []
            for msg in reversed(self.history):
                # If we hit a user message that matches our current query (roughly), stop
                # Or just collect until we hit a ModelRequest that is a user text?
                # PydanticAI messages: ModelRequest (User), ModelResponse (AI)
                
                if isinstance(msg, ModelRequest):
                     # Check if this is the user message we just sent
                     # It will have TextPart with content roughly equal to augmented_message
                     is_current_user_msg = False
                     for part in msg.parts:
                         if isinstance(part, TextPart) and user_message in part.content:
                             is_current_user_msg = True
                             break
                     
                     if is_current_user_msg:
                         break # Stop, we found the start of this turn
                
                current_turn_messages.insert(0, msg)

            for msg in current_turn_messages:
                if isinstance(msg, ModelResponse):
                    for part in msg.parts:
                        if isinstance(part, ToolCallPart):
                            thinking_process.append({
                                "type": "tool_call",
                                "title": f"Call Tool: {part.tool_name}",
                                "content": part.args_as_dict() if hasattr(part, 'args_as_dict') else str(part.args),
                                "icon": "fa-tools"
                            })
                        elif isinstance(part, TextPart):
                            if part.content.strip():
                                thinking_process.append({
                                    "type": "thought",
                                    "title": "Thought",
                                    "content": part.content,
                                    "icon": "fa-lightbulb"
                                })
                elif isinstance(msg, ModelRequest):
                    for part in msg.parts:
                        if isinstance(part, ToolReturnPart):
                            thinking_process.append({
                                "type": "tool_result",
                                "title": f"Result: {part.tool_name}",
                                "content": part.content,
                                "icon": "fa-check-circle"
                            })
            
            # Combine map commands from deps (collected by tools) and response (if any)
            map_commands = deps.map_commands
            if response_data.map_commands:
                map_commands.extend(response_data.map_commands)
            
            return {
                "response": response_data.final_answer,
                "map_commands": map_commands,
                "steps": [step.model_dump() for step in response_data.steps_taken],
                "thinking_process": thinking_process
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "response": f"AI Error: {e}", 
                "thinking_process": [{"type": "error", "title": "Error", "content": str(e), "icon": "fa-exclamation-triangle"}]
            }

# Singleton
mcp_service = MCPService()
