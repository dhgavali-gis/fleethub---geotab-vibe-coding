
import os
from dotenv import load_dotenv
import mygeotab

load_dotenv()

username = os.getenv("GEOTAB_USERNAME")
password = os.getenv("GEOTAB_PASSWORD")
database = os.getenv("GEOTAB_DATABASE")
server = os.getenv("GEOTAB_SERVER")

print(f"Server env: {server}")

api = mygeotab.API(
    username=username, password=password, database=database, server=server
)
api.authenticate()

print(f"API object: {api}")
print(f"Has server attr? {hasattr(api, 'server')}")
if hasattr(api, 'server'):
    print(f"api.server: {api.server}")

print(f"Credentials object: {api.credentials}")
print(f"Credentials Type: {type(api.credentials)}")
print(f"Dir Credentials: {dir(api.credentials)}")

# Check for sessionId specifically
if hasattr(api.credentials, 'sessionId'):
    print(f"api.credentials.sessionId: {api.credentials.sessionId}")
elif hasattr(api.credentials, 'session_id'):
    print(f"api.credentials.session_id: {api.credentials.session_id}")
elif hasattr(api.credentials, 'get'):
    print(f"api.credentials.get('sessionId'): {api.credentials.get('sessionId')}")
else:
    print("Cannot find sessionId in credentials")
