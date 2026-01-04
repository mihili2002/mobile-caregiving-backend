
import requests
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:5000"

def test_fetch_schedule(uid, date, label=""):
    print(f"\n--- [{label}] Fetching schedule for UID: {uid}, Date: {date} ---")
    payload = {"uid": uid, "date": date}
    try:
        response = requests.post(f"{BASE_URL}/api/schedule/get_schedule", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Schedule fetched successfully!")
            print(f"Date: {data.get('date')}")
            tasks = data.get('tasks', [])
            print(f"Tasks Count: {len(tasks)}")
            for t in tasks:
                print(f" - {t['time']} | {t['task_name']} | Completed: {t['completed']} | Type: {t['type']} | ID: {t['id']}")
            return tasks
        else:
            print(f"❌ Failed to fetch schedule: {response.text}")
            return []
    except Exception as e:
         print(f"❌ Connection Failed: {e}")
         return []

def test_add_task(uid, date):
    print(f"\n--- Adding task for UID: {uid}, Date: {date} ---")
    payload = {
        "uid": uid,
        "date": date,
        "task": {
            "task_name": "Verification Task",
            "time": "12:00",
            "type": "test_verification"
        }
    }
    try:
        response = requests.post(f"{BASE_URL}/api/schedule/add_task", json=payload)
        
        if response.status_code == 200:
            print("Task added successfully!")
            return True
        else:
            print(f"Failed to add task: {response.text}")
            return False
    except Exception as e:
        print(f"Connection Failed: {e}")
        return False

if __name__ == "__main__":
    # 1. Past Date (Known Data)
    test_fetch_schedule(
        uid="T9bcdMiMEfRxfvihEQN3KcqskCi1", 
        date="2025-12-17", 
        label="PAST DATE"
    )

    # 2. Current Date (Today)
    today = datetime.now().strftime("%Y-%m-%d")
    uid = "T9bcdMiMEfRxfvihEQN3KcqskCi1"
    
    # Fetch first (might be empty)
    test_fetch_schedule(uid, today, label="TODAY (Before Add)")
    
    # Add a task
    if test_add_task(uid, today):
        # Fetch again to verify addition
        test_fetch_schedule(uid, today, label="TODAY (After Add)")
