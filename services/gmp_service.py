import os
import json
import googlemaps
from datetime import datetime
from typing import Dict, Any, Optional, List

class GMPService:
    def __init__(self):
        # Use GOOGLE_API_KEY from .env (shared with Gemini)
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            print("[GMPService] Warning: GOOGLE_API_KEY is missing.")
            self.client = None
        else:
            try:
                self.client = googlemaps.Client(key=self.api_key)
                print("[GMPService] Google Maps Client initialized.")
            except Exception as e:
                print(f"[GMPService] Initialization Error: {e}")
                self.client = None

    def search_places(self, text_query: str, latitude: float = None, longitude: float = None, radius_meters: int = 5000) -> str:
        """
        Finds places, businesses, or addresses using Google Maps Places API.
        
        Args:
            text_query: The search query (e.g., 'heavy duty truck repair', 'gas station').
            latitude: Optional latitude for location bias (e.g., vehicle's current location).
            longitude: Optional longitude for location bias.
            radius_meters: Search radius in meters (default 5000).
            
        Returns:
            A formatted string list of top 5 places with details.
        """
        if not self.client: return "Error: Google Maps API not configured."
        
        try:
            location_bias = None
            if latitude is not None and longitude is not None:
                # googlemaps python client uses 'location' parameter for bias in places()
                # Format: (lat, lng) tuple or string
                location_bias = (latitude, longitude)
                
            # Use Places API (Text Search)
            # Note: The python client 'places' method corresponds to Text Search
            result = self.client.places(query=text_query, location=location_bias, radius=radius_meters)
            
            if not result.get('results'):
                return f"No places found for '{text_query}' near ({latitude}, {longitude})."
                
            # Format Output for LLM
            output = []
            output.append(f"### Found Places for '{text_query}':")
            
            for place in result['results'][:5]: # Limit to top 5
                name = place.get('name')
                addr = place.get('formatted_address')
                place_id = place.get('place_id')
                rating = place.get('rating', 'N/A')
                user_ratings_total = place.get('user_ratings_total', 0)
                loc = place['geometry']['location']
                open_now = place.get('opening_hours', {}).get('open_now', 'Unknown')
                
                status_icon = "🟢 Open" if open_now is True else "🔴 Closed" if open_now is False else "⚪ Status Unknown"
                
                output.append(
                    f"- **{name}** ({rating}★, {user_ratings_total} reviews)\n"
                    f"  - Address: {addr}\n"
                    f"  - Status: {status_icon}\n"
                    f"  - Location: {loc['lat']}, {loc['lng']}\n"
                    f"  - Place ID: `{place_id}`"
                )
            
            output.append("\n**SYSTEM NOTE**: To show these on the map, call `render_map_tool` for each place with type='marker' and data={'lat': ..., 'lon': ..., 'title': '...', 'snippet': '...'}.")
                
            return "\n".join(output)
        except Exception as e:
            return f"Error searching places: {e}"

    def compute_routes(self, origin: str, destination: str, travel_mode: str = "driving") -> str:
        """
        Computes travel routes, distance, and ETA using Google Maps Directions API.
        
        Args:
            origin: Starting point (address, 'lat,lng', or place_id).
            destination: End point (address, 'lat,lng', or place_id).
            travel_mode: 'driving' (default), 'walking', 'bicycling', 'transit'.
            
        Returns:
            A summary of the best route including distance and duration in traffic.
        """
        if not self.client: return "Error: Google Maps API not configured."
        
        try:
            # Handle "place_id:..." format if passed by LLM (though client handles place_id directly usually)
            # The python client handles place_id automatically if prefixed with 'place_id:'
            # But let's ensure we pass it correctly.
            
            # Directions API
            directions = self.client.directions(
                origin=origin,
                destination=destination,
                mode=travel_mode,
                departure_time=datetime.now(), # Enable traffic estimation
                traffic_model="best_guess"
            )
            
            if not directions:
                return f"No route found from '{origin}' to '{destination}'."
                
            route = directions[0]['legs'][0]
            overview_polyline = directions[0].get('overview_polyline', {}).get('points')
            
            if not overview_polyline:
                return "Route found, but no visualization path available."
            
            # Duration in traffic is preferred if available
            duration_text = route.get('duration_in_traffic', route['duration'])['text']
            distance_text = route['distance']['text']
            start_addr = route['start_address']
            end_addr = route['end_address']
            
            summary = directions[0].get('summary', 'N/A')
            
            steps_summary = []
            for step in route.get('steps', [])[:3]: # First 3 steps preview
                html_instr = step.get('html_instructions', '')
                # Simple strip tags (rough)
                import re
                clean_instr = re.sub('<[^<]+?>', '', html_instr)
                steps_summary.append(f"- {clean_instr} ({step['distance']['text']})")
            
            return (
                f"### Route Calculation:\n"
                f"From: **{start_addr}**\n"
                f"To: **{end_addr}**\n"
                f"- **Distance**: {distance_text}\n"
                f"- **ETA (w/ Traffic)**: {duration_text}\n"
                f"- **Main Route**: {summary}\n"
                f"- **Initial Steps**:\n" + "\n".join(steps_summary) + "\n..."
                f"\n\n**SYSTEM NOTE**: To visualize this route, you MUST call `render_map_tool` with:\n"
                f"type='route', data={json.dumps({'path': overview_polyline, 'origin': start_addr, 'destination': end_addr})}"
            )
        except Exception as e:
            return f"Error computing route: {e}"

# Singleton Instance
gmp_service = GMPService()
