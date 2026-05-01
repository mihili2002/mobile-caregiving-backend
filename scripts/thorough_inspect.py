
import os
from firebase_admin import credentials, firestore, initialize_app

cred_path = r"d:\Users\ASUS\Desktop\Project Backend\mobile-caregiving-backend\app\core\firebase_key.json"
cred = credentials.Certificate(cred_path)
initialize_app(cred)
db = firestore.client()

uid = "f8EMa3cUBvgaZkTqFsfPvDIB8ay1"
print(f"Listing ALL documents in 'schedules' for user {uid}:")

seen_ids = set()
def print_doc(d):
    if d.id in seen_ids: return
    seen_ids.add(d.id)
    data = d.to_dict()
    tasks = data.get('tasks', [])
    print(f"ID: {d.id} | Date: {data.get('date')} | userId: {data.get('userId')} | uid: {data.get('uid')}")
    for t in tasks:
        print(f"  - {t.get('task_name')} at {t.get('time')}")
    print("-" * 20)

docs1 = db.collection('schedules').where("userId", "==", uid).stream()
for d in docs1: print_doc(d)

docs2 = db.collection('schedules').where("uid", "==", uid).stream()
for d in docs2: print_doc(d)
