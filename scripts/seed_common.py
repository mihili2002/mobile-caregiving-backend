
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

tasks = [
    {"task_name": "Wake Up", "default_time": "07:00", "uid": "GLOBAL", "type": "common"},
    {"task_name": "Breakfast", "default_time": "08:30", "uid": "GLOBAL", "type": "common"},
    {"task_name": "Lunch", "default_time": "13:00", "uid": "GLOBAL", "type": "common"},
    {"task_name": "Nap", "default_time": "14:00", "uid": "GLOBAL", "type": "common"},
    {"task_name": "Dinner", "default_time": "19:00", "uid": "GLOBAL", "type": "common"},
    {"task_name": "Sleep", "default_time": "22:00", "uid": "GLOBAL", "type": "common"},
]

def seed():
    collection = db.collection('common_routine_templates')
    for t in tasks:
        # Check if exists to avoid dupes
        exists = collection.where('task_name', '==', t['task_name']).where('uid', '==', 'GLOBAL').get()
        if not exists:
            collection.add(t)
            print(f"Added {t['task_name']}")
        else:
            print(f"Skipped {t['task_name']} (Exists)")

if __name__ == "__main__":
    seed()
