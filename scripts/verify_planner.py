
import requests
import json
import uuid

BASE_URL = "http://127.0.0.1:5000"
UID = "T9bcdMiMEfRxfvihEQN3KcqskCi1"

def test_dynamic_scheduling():
    print(f"\n--- Testing Dynamic Planner for UID: {UID} ---")
    
    # 1. Fetch Suggestions
    try:
        response = requests.get(f"{BASE_URL}/get_daily_suggestions/{UID}")
        if response.status_code == 200:
            data = response.json()
            print("Suggestions fetched.")
            
            meds = data.get('medications', [])
            print(f"Found {len(meds)} medication suggestions.")
            
            for m in meds:
                print(f" - [{m.get('time')}] {m.get('drug_name')} ({m.get('timing_label')})")
                
            # Verification Logic
            # Check if any med has a specific time != 08:00 (default)
            # This depends on data in DB. If empty, we might need to seed data.
            # Assuming 'Metformin' exist from previous steps? Or manual data?
            
            if not meds:
                print("No medications found to verify logic. Please ensure 'patient_medications' has data.")
        else:
            print(f"Failed to fetch: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_dynamic_scheduling()
