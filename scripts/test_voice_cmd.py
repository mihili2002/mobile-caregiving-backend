import requests
import json

# Test the voice command endpoint
url = "http://127.0.0.1:5000/api/ai/process_voice_command"

test_data = {
    "text": "remind me to drink water at 4pm",
    "uid": "test_user_123",
    "session_id": "test_session"
}

try:
    response = requests.post(url, json=test_data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
