import sys
import os

sys.path.append(os.getcwd())
from app.core.firebase import get_db

db = get_db()
schedules = db.collection('schedules').stream()

found = False
for doc in schedules:
    data = doc.to_dict()
    tasks = data.get('tasks', [])
    for task in tasks:
        if str(task.get('id')) == '80530601-ad51-496c-bf19-de82970e0cfc' or task.get('taskId') == '80530601-ad51-496c-bf19-de82970e0cfc':
            print(f"Found Task! Name: {task.get('task_name', 'Unknown')}")
            print(f"Type/Category: {task.get('type', 'None')}")
            found = True
            break
    if found:
        break

if not found:
    print('Task not found in Firestore schedules.')
