
import os
import firebase_admin
from firebase_admin import credentials, firestore

# Setup Firebase
cred_path = r"D:\Users\ASUS\Desktop\Project Backend\mobile-caregiving-backend\app\core\firebase_key.json"
output_file = r"D:\Users\ASUS\Desktop\Project Backend\mobile-caregiving-backend\scripts\find_task_results.log"

def log_to_file(msg):
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")
    print(msg)

if os.path.exists(output_file):
    os.remove(output_file)

cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)
db = firestore.client()

def find_task():
    log_to_file("--- Searching for 'read a book' task ---")
    schedules = db.collection('schedules').stream()
    
    found = False
    for doc in schedules:
        data = doc.to_dict()
        tasks = data.get('tasks', [])
        for t in tasks:
            name = t.get('task_name') or t.get('taskName') or ""
            if 'read a book' in name.lower():
                found = True
                uid = data.get('userId') or data.get('uid')
                log_to_file(f"Found in Schedule Doc: {doc.id}")
                log_to_file(f"  Parent UID/userId: {uid}")
                log_to_file(f"  Task Data: {t}")
                
                # Check Profile
                if uid:
                    profile = db.collection('elder_profiles').document(uid).get()
                    if profile.exists:
                        log_to_file(f"  Profile Data for {uid}: {profile.to_dict()}")
                    else:
                        log_to_file(f"  Profile NOT FOUND for {uid}")
                else:
                    log_to_file("  UID is None in this schedule doc!")

    if not found:
        log_to_file("Task 'read a book' not found in any schedule.")

if __name__ == "__main__":
    find_task()
