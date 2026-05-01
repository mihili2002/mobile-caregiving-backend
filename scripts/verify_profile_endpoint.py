
import requests
import json
import random

BASE_URL = "http://127.0.0.1:8000"

def test_create_profile():
    payload = {
        "uid": f"test_user_v2_{random.randint(1000,9999)}",
        "name": "Test User",
        "age": 75,
        "long_term_illness": "Yes",
        "sleep_well_1to5": 3,
        "tired_day_1to5": 4,
        "forget_recent_1to5": 2,
        "difficulty_remember_tasks_1to5": 3,
        "forget_take_meds_1to5": 1,
        "tasks_harder_1to5": 4,
        "lonely_1to5": 2,
        "sad_anxious_1to5": 1,
        "social_talk_1to5": 5,
        "enjoy_hobbies_1to5": 4,
        "comfortable_app_1to5": 5,
        "reminders_helpful_1to5": 5,
        "reminders_right_time_1to5": 4,
        "reminders_preference": "Gentle Voice" 
    }
    
    print(f"Testing /create_profile with UID: {payload['uid']}...")
    try:
        response = requests.post(f"{BASE_URL}/api/ai/create_profile", json=payload)
        print(f"Status Code: {response.status_code}")
        print("Response:", response.text)
        
        if response.status_code == 201:
            data = response.json()
            if "prediction_probability" in data and "prediction_tier" in data:
                print("SUCCESS: Profile created and Prediction generated!")
                return True
            else:
                print("WARNING: Profile created but Prediction fields missing.")
                return False
        else:
            print("FAILED: Non-201 status code.")
            return False
            
    except Exception as e:
        print(f"ERROR: Could not connect to backend. {e}")
        return False

if __name__ == "__main__":
    test_create_profile()
