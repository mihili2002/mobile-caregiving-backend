import requests
import json
import uuid

# Configuration
BASE_URL = "http://127.0.0.1:5000"
TEST_UID = f"test_user_{uuid.uuid4().hex[:8]}"

def test_create_profile():
    print(f"🔵 Testing /create_profile for UID: {TEST_UID}")
    
    payload = {
        "uid": TEST_UID,
        "name": "Test Elder",
        "age": 75,
        "gender": "Male",
        "mobility_level": "Walker",    # Should map to 1
        "cognitive_level": "Moderate", # Should map to 2
        "mental_health": "Normal"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/create_profile", json=payload)
        
        if response.status_code == 201:
            print("Profile Created Successfully!")
            data = response.json()
            if "ai_stats" in data:
                print("🧠 AI Stats Returned:")
                print(json.dumps(data["ai_stats"], indent=2))
            else:
                print("No AI Stats in response.")
        else:
            print(f"Failed: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    test_create_profile()
