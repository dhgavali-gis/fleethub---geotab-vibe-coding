
import mygeotab
import os
from dotenv import load_dotenv
from mygeotab.exceptions import MyGeotabException, AuthenticationException

# Load environment variables
load_dotenv()

class GeotabClient:
    def __init__(self):
        self.api = None
        self.credentials = self._get_credentials()

    def _get_credentials(self):
        """Retrieve credentials from environment variables."""
        database = os.getenv('GEOTAB_DATABASE')
        username = os.getenv('GEOTAB_USERNAME')
        password = os.getenv('GEOTAB_PASSWORD')
        server = os.getenv('GEOTAB_SERVER', 'my.geotab.com')
        
        if not all([database, username, password]):
            print("Warning: Missing Geotab credentials in .env file.")
            return None
        
        return {
            'database': database,
            'username': username,
            'password': password,
            'server': server
        }

    def authenticate(self):
        """Authenticate with MyGeotab API."""
        if not self.credentials:
            return False

        try:
            # First, create API object
            self.api = mygeotab.API(
                username=self.credentials['username'],
                password=self.credentials['password'],
                database=self.credentials['database'],
                server=self.credentials['server']
            )
            # Then authenticate
            self.api.authenticate()
            print(f"Successfully connected to {self.api.credentials.database}")
            return True
        except AuthenticationException:
            print("Authentication failed. Please check your credentials.")
            return False
        except MyGeotabException as e:
            print(f"Geotab API error: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error during authentication: {e}")
            return False

    def get_api(self):
        """Get the authenticated API object. Re-authenticates if needed."""
        if self.api is None:
            print("API not initialized, authenticating...")
            if not self.authenticate():
                print("Authentication failed in get_api()")
                return None
        return self.api

# Singleton instance
geotab_client = GeotabClient()
