
import os
from firebase_admin import credentials, firestore, initialize_app

# Initialize Firebase
cred_path = r"d:\Users\ASUS\Desktop\Project Backend\mobile-caregiving-backend\app\core\firebase_key.json"
cred = credentials.Certificate(cred_path)
initialize_app(cred)
db = firestore.client()

print("Listing ALL documents in 'schedules' collection:")
docs = db.collection('schedules').stream()
for d in docs:
    data = d.to_dict()
    tasks = data.get('tasks', [])
    print(f"ID: {d.id} | Tasks: {len(tasks)}")
    for t in tasks:
        print(f"  - {t.get('task_name')} at {t.get('time')}")
