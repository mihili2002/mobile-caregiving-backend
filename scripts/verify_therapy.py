
import requests
import json
import uuid

BASE_URL = "http://127.0.0.1:5000"
TEST_ELDER_ID = "test_elder_therapy_001"

def create_dummy_profile():
    print(f"\n--- Creating Dummy Profile for {TEST_ELDER_ID} ---")
    # Using existing endpoint or direct firestore? 
    # Since we are internal, let's use a direct script or just assume /create_profile exists?
    # /create_profile exists in app.py logic? No, let's use the 'verify_therapy.py' to init DB directly or use a known user.
    # Actually, simpler: Use 'verify_therapy.py' to inject profile if we can import firebase stuff? 
    # No, keep it clean. Let's use a known existing user ID if possible or just skip profile check.
    # But for 'get_daily_suggestions', profile check is mandatory.
    
    # Let's create a temporary route or use a known UID.
    # I saw T9bcdMiMEfRxfvihEQN3KcqskCi1 in previous steps. Let's use that.
    pass

# Switched to known existing user to avoid profile creation issues
TEST_ELDER_ID = "T9bcdMiMEfRxfvihEQN3KcqskCi1" 

def test_save_recommendation():
    print(f"\n--- Testing Save Recommendation for {TEST_ELDER_ID} ---")
    
    payload = {
        "elder_id": TEST_ELDER_ID,
        "activity_name": "Chair Yoga",
        "duration": "15 mins",
        "instructions": "Gentle stretching while seated.",
        "assigned_by": "Dr. Smith"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/therapy/save_recommendation", json=payload)
        if response.status_code == 201:
            print("Recommendation Saved Successfully!")
            print(f"Server Response: {response.json()}")
            return True
        else:
            print(f"Failed to save: {response.text}")
            return False
    except Exception as e:
        print(f"Connection Error: {e}")
        return False

def test_fetch_suggestions():
    print(f"\n--- Verifying content via Aggregator /get_daily_suggestions ---")
    try:
        response = requests.get(f"{BASE_URL}/get_daily_suggestions/{TEST_ELDER_ID}")
        if response.status_code == 200:
            data = response.json()
            therapy_list = data.get('therapy', [])
            print(f"Suggestions Fetched. Found {len(therapy_list)} therapy items.")
            
            found = False
            for item in therapy_list:
                print(f" - {item.get('activity_name')} ({item.get('duration')})")
                if item.get('activity_name') == "Chair Yoga":
                    found = True
            
            if found:
                print("Confirmed: 'Chair Yoga' is present in suggestions.")
            else:
                print("'Chair Yoga' NOT found in suggestions!")
        else:
            print(f"Failed to fetch suggestions: {response.text}")
    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    if test_save_recommendation():
        test_fetch_suggestions()
