
import os
from firebase_admin import credentials, firestore, initialize_app

cred_path = r"d:\Users\ASUS\Desktop\Project Backend\mobile-caregiving-backend\app\core\firebase_key.json"
cred = credentials.Certificate(cred_path)
initialize_app(cred)
db = firestore.client()

uid = "f8EMa3cUBvgaZkTqFsfPvDIB8ay1"
print(f"Searching for schedule documents with ID containing {uid}:")

docs = db.collection('schedules').stream()
for d in docs:
    if uid in d.id:
        data = d.to_dict()
        tasks = data.get('tasks', [])
        print(f"ID: {d.id} | Date in doc: {data.get('date')} | Tasks count: {len(tasks)}")
        for t in tasks:
            print(f"  - {t.get('task_name')} at {t.get('time')}")
        print("-" * 30)
