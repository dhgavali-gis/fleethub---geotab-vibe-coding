
import asyncio
from datetime import datetime, timedelta
from mygeotab.exceptions import MyGeotabException
import time
import requests
import json
from services.safety_service import get_vehicle_risk_events_with_location

class AceService:
    def __init__(self):
        pass

    async def generate_coaching_advice(self, api, device_id, device_name, stats):
        """
        Orchestrate the Ace interaction: Create Chat -> Send Prompt -> Poll Results
        Uses raw JSON-RPC to bypass SDK issues with GetAceResults.
        """
        try:
            # Extract credentials and server from API object
            creds = api.credentials
            
            # 1. Create Chat
            chat_id = self._raw_rpc_call(api, 'create-chat', {})
            if not chat_id:
                return "Error: Could not initialize AI chat session (Raw RPC failed)."

            # 1.5 Fetch Location Specific Risks (Enrichment)
            risk_locations = get_vehicle_risk_events_with_location(api, device_id)

            # 2. Construct Prompt
            prompt = self._construct_prompt(device_name, stats, risk_locations)
            
            # 3. Send Prompt
            message_group_id = self._raw_rpc_call(api, 'send-prompt', {
                'chat_id': chat_id,
                'prompt': prompt
            })
            if not message_group_id:
                return "Error: Failed to send prompt to AI."

            # 4. Poll for Results (Pass chat_id for validation)
            result = await self._poll_results_raw(api, message_group_id, chat_id)
            return result

        except Exception as e:
            print(f"[AceService] Error: {e}")
            return f"Error: AI service exception: {str(e)}"

    def _raw_rpc_call(self, api, function_name, params):
        """
        Execute a raw JSON-RPC call to GetAceResults using requests.
        Bypasses mygeotab-python SDK serialization issues.
        """
        try:
            url = f"https://{api.credentials.server}/apiv1"
            
            payload = {
                "method": "GetAceResults",
                "params": {
                    "serviceName": "dna-planet-orchestration",
                    "functionName": function_name,
                    "customerData": True,
                    "functionParameters": params,
                    "credentials": {
                        "database": api.credentials.database,
                        "sessionId": api.credentials.session_id,
                        "userName": api.credentials.username
                    }
                }
            }
            
            print(f"[AceService] Raw RPC: {function_name}...")
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # DEBUG: Print Raw Response to see what's happening
            print(f"[AceService] Raw Response for {function_name}: {data}")
            
            if 'error' in data:
                print(f"[AceService] RPC Error: {data['error']}")
                return None
                
            if 'result' in data and data['result'].get('apiResult'):
                results = data['result']['apiResult'].get('results', [])
                if results:
                    if function_name == 'create-chat':
                        return results[0].get('chat_id')
                    elif function_name == 'send-prompt':
                        # Handle nested message_group object
                        mg = results[0].get('message_group', {})
                        return mg.get('id') or results[0].get('message_group_id')
                    elif function_name == 'get-message-group':
                        return results[0] # Return full object for polling
            
            print(f"[AceService] Unexpected response structure: {data}")
            return None
            
        except Exception as e:
            print(f"[AceService] Raw RPC Exception: {e}")
            return None

    def _construct_prompt(self, device_name, stats, risk_locations):
        """Construct a VERY CONCISE prompt (<500 chars) for Ace API."""
        
        # 1. Compress Stats & Determine Context
        summary_parts = []
        total_events = 0
        is_critical = False
        
        for rule, count in stats.items():
            short_name = rule.replace('Rule', '').replace('Id', '')
            summary_parts.append(f"{short_name}({count}x)")
            total_events += count
            if 'Collision' in rule or 'Engine' in rule:
                is_critical = True
                
        summary_str = ", ".join(summary_parts)
        
        # 2. Dynamic Tone
        tone = "Objective"
        if is_critical or total_events > 10:
            tone = "URGENT/Strict"
        elif total_events > 5:
            tone = "Firm"
            
        # 3. Compress Locations
        loc_str = ""
        if risk_locations:
            loc_str = "Locs:"
            for i, item in enumerate(risk_locations[:2]): 
                r_name = item['rule_name'].split(' ')[0] 
                lat = f"{item['latitude']:.3f}"
                lon = f"{item['longitude']:.3f}"
                loc_str += f"{r_name}@{lat},{lon};"
        
        # 4. Instructions
        # Force specific actions: "Schedule repair", "Coach driver"
        prompt = (
            f"Role:Fleet Mgr. Target:'{device_name}'. "
            f"Data:{summary_str}. {loc_str} "
            f"Tone:{tone}. "
            f"Task:List 3 actions. MUST mention specific Lat/Lon of risks if data exists. "
            f"NO markdown. NO fluff. Use IMPERATIVE verbs. "
            f"Format:[Issue]@[Location]->[Action]. "
            f"Lang:English."
        )
        
        # Debug length
        print(f"[AceService] Prompt Length: {len(prompt)} chars")
        return prompt

    # _create_chat and _send_prompt are replaced by _raw_rpc_call

    async def execute_ace_query(self, api, prompt):
        """
        Execute a full Ace query flow: Create Chat -> Send Prompt -> Poll -> Get CSV URL.
        Returns the CSV URL or raw data for DuckDB ingestion.
        """
        try:
            # 1. Create Chat
            chat_id = self._raw_rpc_call(api, 'create-chat', {})
            if not chat_id:
                return {"error": "Could not initialize AI chat session."}

            # 2. Send Prompt
            message_group_id = self._raw_rpc_call(api, 'send-prompt', {
                'chat_id': chat_id,
                'prompt': prompt
            })
            if not message_group_id:
                return {"error": "Failed to send prompt to AI."}

            # 3. Poll for Results
            result = await self._poll_results_raw(api, message_group_id, chat_id, return_full_object=True)
            
            if isinstance(result, dict) and 'error' in result:
                return result
                
            # 4. Extract CSV URL
            # The result from _poll_results_raw (with return_full_object=True) is the message object
            # We need to find the signed_url in it.
            csv_url = self._find_csv_url(result)
            
            if csv_url:
                return {"csv_url": csv_url, "chat_id": chat_id, "message_group_id": message_group_id}
            else:
                # Fallback: Return the text content if no CSV found (for simple queries)
                content = result.get('content') or result.get('reasoning') or "No data returned."
                # CRITICAL FIX: If Ace returns a query but no CSV, it might be a small result set embedded in the response
                # We should try to parse the 'preview_array' or similar if available
                return {"text_result": content}

        except Exception as e:
            print(f"[AceService] Query Error: {e}")
            return {"error": f"AI service exception: {str(e)}"}

    def _find_csv_url(self, obj):
        """Recursively search for CSV URL in the response object."""
        if isinstance(obj, str):
            if obj.startswith('https://') and ('.csv' in obj or 'storage.googleapis.com' in obj):
                return obj
        
        if isinstance(obj, dict):
            # Check signed_urls directly first
            if 'signed_urls' in obj and isinstance(obj['signed_urls'], list) and obj['signed_urls']:
                return obj['signed_urls'][0]
                
            for key, value in obj.items():
                found = self._find_csv_url(value)
                if found: return found
                
        if isinstance(obj, list):
            for item in obj:
                found = self._find_csv_url(item)
                if found: return found
                
        return None

    async def _poll_results_raw(self, api, message_group_id, chat_id, return_full_object=False):
        """Step 3: Poll using Raw RPC"""
        max_attempts = 30
        delay = 5
        
        print(f"[AceService] Polling results for {message_group_id}...")
        
        for attempt in range(max_attempts):
            await asyncio.sleep(delay)
            
            result_obj = self._raw_rpc_call(api, 'get-message-group', {
                'message_group_id': message_group_id,
                'chat_id': chat_id 
            })
            
            if not result_obj:
                continue
                
            group_data = result_obj.get('message_group', {})
            status = group_data.get('status', {}).get('status')
            
            print(f"[AceService] Poll attempt {attempt+1}: {status}")
            
            if status == 'DONE':
                messages = group_data.get('messages', {})
                for msg_id, msg in messages.items():
                    if msg.get('role') == 'assistant':
                        if return_full_object:
                            return msg
                        return msg.get('content') or msg.get('reasoning') or "AI finished but returned no text."
                return {"error": "AI analysis complete, but response format was unexpected."}
            
            if status == 'FAILED':
                print(f"[AceService] Server reported FAILED status. Retrying...")
                continue
                
        return {"error": "AI timeout. Please try again later."}

# Singleton
ace_service = AceService()
