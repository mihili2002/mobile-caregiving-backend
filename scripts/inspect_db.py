
import os
import json
from firebase_admin import credentials, firestore, initialize_app
from datetime import datetime

# Initialize Firebase
cred_path = r"d:\Users\ASUS\Desktop\Project Backend\mobile-caregiving-backend\app\core\firebase_key.json"
if not os.path.exists(cred_path):
    print(f"Error: Firebase key not found at {cred_path}")
    exit(1)

cred = credentials.Certificate(cred_path)
initialize_app(cred)
db = firestore.client()

uid = "f8EMa3cUBvgaZkTqFsfPvDIB8ay1"
today = datetime.now().strftime("%d.%m.%Y")
doc_id = f"{uid}_{today}"

print(f"Checking document: {doc_id}")
doc = db.collection('schedules').document(doc_id).get()

if doc.exists:
    data = doc.to_dict()
    print("Document found!")
    print(f"UserId in doc: {data.get('userId')}")
    print(f"UID in doc: {data.get('uid')}")
    print(f"Date in doc: {data.get('date')}")
    print(f"Status in doc: {data.get('status')}")
    print("\nTasks found:")
    tasks = data.get('tasks', [])
    for i, t in enumerate(tasks):
        print(f"{i+1}. {t.get('task_name')} at {t.get('time')} (ID: {t.get('id')})")
else:
    print("Document NOT found!")

print("\nListing all schedules for this user:")
docs = db.collection('schedules').where("userId", "==", uid).stream()
for d in docs:
    print(f"- {d.id}")

docs2 = db.collection('schedules').where("uid", "==", uid).stream()
for d in docs2:
    print(f"- {d.id} (found via uid field)")
