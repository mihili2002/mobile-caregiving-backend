import requests
import json

BASE_URL = "http://127.0.0.1:8000"
TEST_UID = "test_elder_123"

def test_recall_api():
    print("--- Testing /api/ai/recall_memory ---")
    
    payload = {
        "text": "Did I take my medicine today?",
        "uid": TEST_UID
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/ai/recall_memory", json=payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("SUCCESS: Recall endpoint returned successfully.")
        else:
            print(f"FAILURE: Unexpected status code {response.status_code}")
            
    except Exception as e:
        print(f"ERROR: Could not connect to backend: {e}")

if __name__ == "__main__":
    test_recall_api()
