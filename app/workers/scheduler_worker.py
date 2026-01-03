
import threading
import time
from datetime import datetime, timedelta
from firebase_admin import firestore
import traceback
from google.cloud.firestore import FieldFilter
from google.api_core.exceptions import RetryError, ServiceUnavailable

def start_scheduler():
    thread = threading.Thread(target=_run_job, daemon=True)
    thread.start()

def _run_job():
    # print("Background Scheduler Started: Checking for missed tasks every 5 minutes...")
    while True:
        try:
            check_missed_tasks()
        except (RetryError, ServiceUnavailable) as e:
            print(f"Network Error in scheduler loop: {e}. Retrying in 5 mins...")
        except Exception as e:
            print(f"Error in scheduler job: {e}")
            traceback.print_exc()
        
        # Sleep for 5 minutes
        time.sleep(300)

def check_missed_tasks():
    db = firestore.client()
    now = datetime.now()
    
    # Support both formats for transition (Query logic is harder with OR, so let's check one or both?)
    # User requested YYYY-MM-DD. So we prioritize that.
    today_iso = now.strftime("%Y-%m-%d")
    
    # Query today's schedules using YYYY-MM-DD
    schedules = db.collection('schedules').where(filter=FieldFilter('date', '==', today_iso)).stream()
    
    # NOTE: If we need legacy support for DD.MM.YYYY, we might need a separate query or rely on doc IDs.
    
    for doc in schedules:
        data = doc.to_dict()
        tasks = data.get('tasks', [])
        elder_id = data.get('userId') or data.get('uid')
        updated = False
        
        for task in tasks:
            # 1. Filter eligible tasks
            status = task.get('status', 'scheduled')
            if status != 'scheduled':
                continue
                
            # Skip if already completed
            if task.get('completed') is True or task.get('isCompleted') is True:
                continue

            # 2. Get Scheduled Time
            scheduled_time_str = task.get('scheduledAt') or task.get('scheduledTime')
            grace_minutes = task.get('graceMinutes', 30)
            
            # If no scheduledTime, try to construct from 'time' field (HH:MM)
            cutoff_time = None
            if scheduled_time_str:
                try:
                    sch_dt = datetime.fromisoformat(scheduled_time_str)
                    cutoff_time = sch_dt + timedelta(minutes=grace_minutes)
                except:
                    pass
            else:
                 # Check 'time' or 'Time'
                 t_str = task.get('time') or task.get('Time')
                 if t_str:
                    try:
                        # Construct from today's date + HH:MM
                        time_parts = t_str.split(':')
                        sch_dt = datetime(now.year, now.month, now.day, int(time_parts[0]), int(time_parts[1]))
                        cutoff_time = sch_dt + timedelta(minutes=grace_minutes)
                    except:
                        pass
            
            if not cutoff_time:
                continue
                
            # 3. Check Condition: Now > Cutoff
            if now > cutoff_time:
                print(f"Marking Task MISSED: {task.get('task_name')} for {elder_id}")
                
                # UPDATE STATUS
                task['status'] = 'missed'
                updated = True
                
                # LOG EVENT to task_events
                try:
                    db.collection('task_events').add({
                        "uid": elder_id,
                        "scheduleDocId": doc.id,
                        "taskId": task.get('id') or task.get('taskId'),
                        "type": "TASK_MISSED",
                        "at": now.isoformat(),
                        "meta": {
                            "task_name": task.get('task_name') or task.get('taskName'),
                            "category": task.get('type') or 'common',
                            "scheduled_time": scheduled_time_str,
                            "grace_minutes": grace_minutes,
                            "reason": "backend_auto_mark_v2"
                        },
                        "created_at": datetime.utcnow()
                    })
                except Exception as ex:
                    print(f"Failed to log TASK_MISSED: {ex}")

        # 4. Save updates to Firestore if any task changed
        if updated:
            doc.reference.update({"tasks": tasks})
