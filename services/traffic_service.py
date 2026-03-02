
import os
import requests
from dotenv import load_dotenv

load_dotenv()

class TrafficService:
    def __init__(self):
        self.api_key = os.getenv('TOMTOM_API_KEY')
        if not self.api_key or self.api_key == 'YOUR_TOMTOM_API_KEY':
            print("[TrafficService] Warning: TOMTOM_API_KEY is missing or invalid.")

    def get_bounding_box(self, lat, lon, offset=0.02):
        """
        Convert a single point to a Bounding Box string (minLon,minLat,maxLon,maxLat).
        offset=0.02 is roughly 2km radius.
        """
        min_lat = lat - offset
        max_lat = lat + offset
        min_lon = lon - offset
        max_lon = lon + offset
        
        # TomTom requires: minLon,minLat,maxLon,maxLat
        return f"{min_lon},{min_lat},{max_lon},{max_lat}"

    def check_nearby_incidents(self, lat, lon):
        """
        Check for traffic incidents around a specific location.
        Returns a list of incidents with type and description.
        """
        if not self.api_key:
            return []

        bbox = self.get_bounding_box(lat, lon)
        
        # GraphQL-like fields selection
        fields = "{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,events{description,code}}}}"
        
        url = "https://api.tomtom.com/traffic/services/5/incidentDetails"
        params = {
            "key": self.api_key,
            "bbox": bbox,
            "fields": fields,
            "language": "en-US",
            "timeValidityFilter": "present"
        }
        
        try:
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            incidents = []
            if 'incidents' in data:
                for inc in data['incidents']:
                    props = inc.get('properties', {})
                    # Filter for specific categories if needed (e.g. 1=Accident, 6=Jam)
                    # For now, return all to let frontend decide
                    incidents.append({
                        'category': props.get('iconCategory'),
                        'description': props.get('events', [{}])[0].get('description', 'Unknown Incident'),
                        'magnitude': props.get('magnitudeOfDelay'),
                        'coordinates': inc.get('geometry', {}).get('coordinates')
                    })
            
            return incidents
            
        except Exception as e:
            print(f"[TrafficService] Error checking incidents: {e}")
            return []

traffic_service = TrafficService()
