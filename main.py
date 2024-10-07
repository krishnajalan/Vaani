from fastapi import FastAPI, Request, BackgroundTasks, Form
from urllib.parse import parse_qs
from pydantic import BaseModel
from twilio.rest import Client
import os
from typing import List, Optional
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import plyvel
import json
from weather import get_token, get_weather_data
from ai import ask_expert
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

weather_token = None
WEATHER_USER = os.environ.get('WEATHER_USER')
WEATHER_PASSWORD = os.environ.get('WEATHER_PASSWORD')

# Twilio Config
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')
TWILIO_API_URL = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Initialize Plyvel DB
db = plyvel.DB('users_db', create_if_missing=True)

# Scheduler to send periodic weather reports
scheduler = BackgroundScheduler()
scheduler.start()

class User(BaseModel):
    user_id: str
    name: str
    conversation: List[str] = []
    Location: str = ""

    @classmethod
    def parse_raw(cls, user_data:str):
        return User(**json.loads(user_data))

MAX_CONVERSATION_LENGTH = 10

class Message(BaseModel):
    SmsMessageSid: str
    ProfileName: str
    Body: str
    From: str
    To: str
    MessageType: str
    Latitude: Optional[str] = None
    Longitude: Optional[str] = None

    @classmethod
    def parse_body(cls, raw_body: str):
        parsed_data = parse_qs(raw_body)
        sms_message_sid = parsed_data.get("SmsMessageSid", [""])[0]
        body = parsed_data.get("Body", [""])[0]
        from_field = parsed_data.get("From", [""])[0]
        to_field = parsed_data.get("To", [""])[0]
        message_type = parsed_data.get("MessageType", [""])[0]
        latitude = parsed_data.get("Latitude", [''])[0]
        longitude = parsed_data.get("Longitude", [''])[0]
        profile_name = parsed_data.get("ProfileName", 'User')[0]

        return cls(
            SmsMessageSid=sms_message_sid,
            Body=body,
            From=from_field,
            To=to_field,
            MessageType=message_type,
            Latitude=latitude,
            Longitude=longitude,
            ProfileName=profile_name
        )

@app.post("/message")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    message_body = await request.body()
    message = Message.parse_body(message_body.decode())
    
    user_id = message.From.split(":")[-1]
    body = [message.Body]
    profile_name = message.ProfileName

    # Retrieve user data from Plyvel
    user_data = db.get(user_id.encode())
    print("User id found: ", user_id.encode(), user_data)
    if user_data:
        print(f"User data found: {user_data}", user_id.encode())
        user = User.parse_raw(user_data)
    else:
        user = User(user_id=user_id, conversation=body, name=profile_name)

    print(f"Message received from {user_id}: {body}", message_body)

    if message.Latitude and message.Longitude:
        print(f"Location received: {message.Latitude}, {message.Longitude}")
        user.Location = f"{message.Latitude},{message.Longitude}"

    # Update conversation history
    user.conversation.append(message.Body)
    user.conversation = user.conversation[-MAX_CONVERSATION_LENGTH:]  # Keep last 10 messages

    # Store updated user data back to Plyvel
    db.put(user_id.encode(), user.json().encode(), sync=True)
    print(f"User data updated: {db.get(user_id.encode())}")

    background_tasks.add_task(process_message, user_id, profile_name, user.conversation)
    return {"status": "Message received"}

async def process_message(user_id: str, profile_name:str, context: List[str]):
    response = await get_llm_response(profile_name, context)
    context.append(f"Vani: {response}")

    # Update user's conversation context, limit to the last 10 messages
    user = User.parse_raw(db.get(user_id.encode()))
    user.conversation.append(response)
    user.conversation = user.conversation[-MAX_CONVERSATION_LENGTH:]
    db.put(user_id.encode(), user.json().encode())

    print(f"Sending response to {user_id}: {response}")

    # Send the LLM response back to the user
    send_message_via_twilio(user_id, response)

async def get_llm_response(name:str, context: List[str]) -> str:
    # Placeholder response from the Bot
    return ask_expert(context[-1], name, context)

@app.post("/send_message")
def send_message_via_twilio(to: str, message: str):
    response = twilio_client.messages.create(
        from_=f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
        to=f"whatsapp:{to}",
        body=message
    )
    return response.sid

@app.get("/send_weather_report")
async def send_weather_report():
    print("Sending weather report to all users")
    for user_id, user_data in db:
        if user_data:
            # load the user_data json string into User object
            user = User(**json.loads(user_data))
            location = user.Location or None
            if location is None:
                send_message_via_twilio(user_id.decode(), "Please share your location to get the weather report")
                continue
            weather_report = await get_weather_report(location)
            user.conversation.append(f"Weather report ko format kr k presentable reponse share kro: {weather_report}")
            formatted_weather_report = await get_llm_response(user.name, user.conversation)
            send_message_via_twilio(user_id.decode(), formatted_weather_report)
    return {"status": "Weather report sent"}

async def get_weather_report(location: str) -> str:
    global weather_token
    weather_token = weather_token or get_token(WEATHER_USER, WEATHER_PASSWORD)
    data = get_weather_data(weather_token, location)
    return f"Weather in {location}: {data}"

def schedule_weather_report():
    scheduler.add_job(send_weather_report, 'cron', minute=1, hour=0)

# Run the scheduling function to send weather reports
schedule_weather_report()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
