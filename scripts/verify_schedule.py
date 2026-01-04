import requests
import json
import uuid
from datetime import datetime

# Configuration
BASE_URL = "http://127.0.0.1:5000"
TEST_UID = "test_user_schedule_001" 

def test_add_schedule_task():
    print(f"Testing /add_task and Schedule Storage for: {TEST_UID}")
    
    # 1. Add Task #1
    task1 = {
        "uid": TEST_UID,
        "task_name": "Morning Walk",
        "time_string": "08:00",
        "type": "common"
    }
    
    try:
        print("\n--- Adding Task 1 ---")
        res1 = requests.post(f"{BASE_URL}/add_task", json=task1)
        if res1.status_code == 201:
            d = res1.json()
            print("Task 1 Added.")
            if "schedule_entry" in d:
                print(f"   Schedule Entry: #{d['schedule_entry']['taskNumber']} - {d['schedule_entry']['taskName']}")
            else:
                print("'schedule_entry' missing in response!")
        else:
             print(f"Failed: {res1.text}")
             
        # 2. Add Task #2 (Check Increment)
        task2 = {
            "uid": TEST_UID,
            "task_name": "Take Vitamins",
            "time_string": "09:00",
            "type": "medication"
        }
        
        print("\n--- Adding Task 2 ---")
        res2 = requests.post(f"{BASE_URL}/add_task", json=task2)
        if res2.status_code == 201:
             d = res2.json()
             print("Task 2 Added.")
             entry = d.get('schedule_entry', {})
             print(f"   Schedule Entry: #{entry.get('taskNumber')} - {entry.get('taskName')}")
             
             if entry.get('taskNumber') == 2:
                 print("Task Numbering works!")
             else:
                 print(f"Task Numbering wrong. Expected 2, got {entry.get('taskNumber')}")
        else:
             print(f"Failed: {res2.text}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_add_schedule_task()
