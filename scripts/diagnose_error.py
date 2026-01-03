
import requests
import json
import time

BASE_URL = "http://127.0.0.1:5000"

def test_endpoint(name, method, url, data=None):
    print(f"\n[{name}] Testing {url} ...")
    try:
        if method == "GET":
            response = requests.get(url)
        else:
            response = requests.post(url, json=data)
        
        print(f"Status: {response.status_code}")
        if response.status_code != 200:
            print("ERROR BODY:")
            print(response.text)
        else:
            print("OK")
            # print(response.json())
            
    except Exception as e:
        print(f"EXCEPTION: {e}")

# 1. Test Voice Command (Dialogflow path)
test_endpoint(
    "1. Voice (Dialogflow)", 
    "POST", 
    f"{BASE_URL}/api/ai/process_voice_command",
    {"text": "remind me to sleep", "uid": "test_diagnose", "session_id": "test_session"}
)

# 2. Test Get Schedule
test_endpoint(
    "2. Get Schedule", 
    "POST", 
    f"{BASE_URL}/api/schedule/get_schedule",
    {"uid": "test_diagnose", "date": "2025-12-31"}
)

# 3. Test Check Profile
test_endpoint(
    "3. Check Profile", 
    "GET", 
    f"{BASE_URL}/api/ai/check_profile/test_diagnose"
)
