import requests
import json
import os
from datetime import datetime, timedelta
# API Endpoint and Key

API_KEY = os.environ.get('API_KEY')
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={API_KEY}"

headers = {
    'Content-Type': 'application/json'
}

# Function to get the Kc value based on the crop and days passed
def get_crop_stage_info(crop, days_passed):
    crop_data = {
        # Cereal Crops
        "Wheat": {"initial": [0, 20, 0.3], "development": [21, 40, 0.7], "mid": [41, 90, 1.15], "late": [91, 120, 0.55]},
        "Corn": {"initial": [0, 15, 0.3], "development": [16, 35, 0.85], "mid": [36, 80, 1.2], "late": [81, 110, 0.55]},
        "Rice": {"initial": [0, 30, 1.0], "development": [31, 60, 1.1], "mid": [61, 100, 1.2], "late": [101, 140, 0.75]},
        "Barley": {"initial": [0, 20, 0.3], "development": [21, 50, 0.7], "mid": [51, 85, 1.1], "late": [86, 120, 0.4]},

        # Vegetable Crops
        "Tomato": {"initial": [0, 30, 0.6], "development": [31, 50, 1.15], "mid": [51, 80, 1.2], "late": [81, 120, 0.8]},
        # Add other crops as needed...
    }

    stages = crop_data.get(crop)
    if stages:
        if stages["initial"][0] <= days_passed <= stages["initial"][1]:
            return stages["initial"][2]  # Kc value
        elif stages["development"][0] <= days_passed <= stages["development"][1]:
            return stages["development"][2]
        elif stages["mid"][0] <= days_passed <= stages["mid"][1]:
            return stages["mid"][2]
        elif stages["mid"][0] < days_passed:
            return stages["late"][2]
    return None

# Function to fetch evapotranspiration data for the next day
def get_evapotranspiration(latitude, longitude):
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%dT12:00:00Z')
    url = f"https://api.meteomatics.com/{tomorrow}/evapotranspiration_24h:mm/{latitude},{longitude}/json"
    username = 'nasa_ranwa_ayush'
    password = '<PASS>'

    response = requests.get(url, auth=(username, password))

    if response.status_code == 200:
        data = response.json()
        return data["data"][0]["coordinates"][0]["dates"][0]["value"]
    else:
        raise Exception("Failed to fetch evapotranspiration data")

def get_precipitation(latitude=26.9124, longitude=75.7873):
    tomorrow_start = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z')
    tomorrow_end = (datetime.utcnow() + timedelta(days=2)).strftime('%Y-%m-%dT00:00:00Z')

    url = f"https://api.meteomatics.com/{tomorrow_start}--{tomorrow_end}:PT5M/precip_1h:mm/{latitude},{longitude}/json"
    username = 'nasa_ranwa_ayush'
    password = '<PASS>'

    response = requests.get(url, auth=(username, password))

    if response.status_code == 200:
        data = response.json()
        return sum([entry['value'] for entry in data['data'][0]['coordinates'][0]['dates']])
    else:
        raise Exception("Failed to fetch precipitation data")

# Function to calculate the irrigation requirement based on user input
def calculate_irrigation(crop, days_passed, latitude, longitude):
    # Get the Kc value based on the crop and days passed
    kc_value = get_crop_stage_info(crop, days_passed)

    if kc_value:
        # Fetch evapotranspiration and precipitation values for tomorrow
        eto = get_evapotranspiration(latitude, longitude)
        precipitation = get_precipitation(latitude, longitude)

        # Calculate crop evapotranspiration (ETc)
        etc = eto * kc_value

        # Calculate next day's irrigation requirement
        irrigation_req = etc - precipitation
        irrigation_req = max(irrigation_req, 0)  # Ensure non-negative values

        return irrigation_req
    else:
        return None


def ask_expert(question, username, context):

    # Check if the question is related to water
    if "पानी" in question.lower() or "water" in question.lower() or "pani" in question.lower():
        # Default values
        crop = "Rice"  # Hardcoded crop name
        days_passed = 30  # Hardcoded days since seeding
        latitude = 26.9124  # Default latitude
        longitude = 75.7873  # Default longitude

        # Check if the username is valid
        valid_usernames=["Dd","mahesh"]

        if username in valid_usernames:

            # Use hardcoded details if username matches
            irrigation_req = calculate_irrigation(crop, days_passed, latitude, longitude)
            if irrigation_req is not None:
                answer = f" तुम्हारी {crop}  फसल में अभी सिंचाई के आवश्यकता: {irrigation_req:.2f} mm"
            else:
                answer = "खेद, फसल या दिन संख्या मान्य नहीं बा।"
        else:
            answer = "खेद, रउआ के यूजरनेम मान्य नहीं बा।"

        context.append(f"वाणी: {answer}")
        return answer

    # Combine the previous messages with the current question
    context_prompt = "\n".join(context) + "\n\n" + "राउर एक कृषि विशेषज्ञ हईं। राउर काम बाय की शेतकरे के सवालन के भोजपुरी में जवाब देब। " \
                    "राउर टमाटर, गेहूँ, चना, चावल, आ कई तरह के फसलन के खेती के बारे में सलाह देवे के चाहीं। " \
                    "राउर जवाब में काम के तरीका के बिस्तार से जानकारी होखो, " \
                    "जइसन की फसल के तैयारी, सही जलवायु, माटी के स्थिति, खाद के उपयोग, सिंचाई के तरीका आ अउरी जरूरी जानकारी।"

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": context_prompt
                    }
                ]
            }
        ]
    }

    # Make the POST request to the API
    response = requests.post(url, headers=headers, data=json.dumps(data))

    # Check the response and return the result
    if response.status_code == 200:
        result = response.json()
        answer = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'No response')

        # Add the response to the conversation history
        context.append(f"वाणी: {answer}")
        return answer
    else:
        return f"Request failed with status code {response.status_code}"
