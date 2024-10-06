import requests
import base64
from datetime import datetime, timezone

def get_token(username: str, password: str) -> str:
    try:        
        # Create the basic authentication header
        auth = f"{username}:{password}"
        encoded_auth = base64.b64encode(auth.encode()).decode()

        # Set up the headers
        headers = {
            'Authorization': f'Basic {encoded_auth}'
        }
        response = requests.get('https://login.meteomatics.com/api/v1/token', headers=headers)
        response.raise_for_status()  # Raise an error for bad responses
        data = response.json()
        token = data.get('access_token')
        return token
    except requests.exceptions.RequestException as err:
        print('something went wrong', err)

def get_weather_data(token: str, location) -> dict:
    try:
        now_utc = datetime.now(timezone.utc)
        formatted_time = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        print('formatted_time', formatted_time)
        response = requests.get(f'https://api.meteomatics.com/{formatted_time}/t_2m:C,precip_1h:mm,wind_speed_10m:ms/{location}/json?access_token={token}')
        response.raise_for_status()  # Raise an error for bad responses
        data = response.json()
        return data.get('data')
    except requests.exceptions.RequestException as err:
        print('something went wrong', err)
