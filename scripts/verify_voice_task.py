
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def verify_voice_task():
    print(f"[{datetime.now()}] Searching for recent voice tasks...")
    
    # 1. Get all schedules (since we don't know the specific UID/Date easily without input)
    # limit to recent ones if possible, but Firestore doesn't sort by time natively on doc IDs easily without a field.
    # We will iterate through recent schedules.
    
    docs = db.collection('schedules').stream()
    
    found_count = 0
    
    for doc in docs:
        data = doc.to_dict()
        tasks = data.get('tasks', [])
        
        for task in tasks:
            if task.get('created_via') == 'voice':
                print(f"\n✅ FOUND VOICE TASK in Doc {doc.id}")
                print(f"   Task Name: {task.get('task_name')}")
                print(f"   Time: {task.get('time')}")
                print(f"   ScheduledAt: {task.get('scheduledAt')}")
                print(f"   Created Via: {task.get('created_via')}")
                print("-" * 30)
                found_count += 1

    if found_count == 0:
        print("❌ No tasks found with created_via='voice'.")
    else:
        print(f"\nTotal Voice Tasks Found: {found_count}")

if __name__ == "__main__":
    verify_voice_task()
