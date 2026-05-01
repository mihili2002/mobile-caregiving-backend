
import os
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# Setup Firebase
cred_path = r"D:\Users\ASUS\Desktop\Project Backend\mobile-caregiving-backend\app\core\firebase_key.json"
output_file = r"D:\Users\ASUS\Desktop\Project Backend\mobile-caregiving-backend\scripts\debug_results.log"

def log_to_file(msg):
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")
    print(msg)

if os.path.exists(output_file):
    os.remove(output_file)

if not os.path.exists(cred_path):
    log_to_file(f"Error: Credentials not found at {cred_path}")
    exit(1)

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
db = firestore.client()

def debug_schedules():
    log_to_file("--- Inspecting Schedules ---")
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        schedules = db.collection('schedules').where('date', '==', today).stream()
        
        found_any = False
        for doc in schedules:
            found_any = True
            data = doc.to_dict()
            uid = data.get('userId') or data.get('uid')
            log_to_file(f"Doc ID: {doc.id}, UID/userId: {uid}, Tasks: {len(data.get('tasks', []))}")
            
        if not found_any:
            log_to_file(f"No schedules found for {today}")
    except Exception as e:
        log_to_file(f"Error checking today's schedules: {e}")

    log_to_file("\n--- Inspecting All Schedules for None/null UIDs ---")
    try:
        all_docs = db.collection('schedules').stream()
        for doc in all_docs:
            data = doc.to_dict()
            uid = data.get('userId') or data.get('uid')
            if uid is None or uid == "None" or uid == "":
                log_to_file(f"⚠️ FOUND BAD DOC: {doc.id}")
                log_to_file(f"  Data fields: {list(data.keys())}")
                log_to_file(f"  UID value: {uid!r}")
    except Exception as e:
        log_to_file(f"Error checking all schedules: {e}")

if __name__ == "__main__":
    debug_schedules()
