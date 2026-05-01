
import threading
import time
from datetime import datetime, timedelta, timezone
from firebase_admin import firestore
import traceback
from google.cloud.firestore import FieldFilter
from google.api_core.exceptions import RetryError, ServiceUnavailable
from app.services.voice_service import voice_service
from app.services.notification_service import send_voice_reminder_notification

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
        
        # Sleep for 1 minute for precise voice reminders
        time.sleep(60)

def check_missed_tasks():
    db = firestore.client()
    now = datetime.now()
    
    # Support both formats for transition (Query logic is harder with OR, so let's check one or both?)
    # User requested YYYY-MM-DD. So we prioritize that.
    today_iso = now.strftime("%Y-%m-%d")
    
    # Query today's schedules using YYYY-MM-DD
    schedules = list(db.collection('schedules').where(filter=FieldFilter('date', '==', today_iso)).stream())
    
    if not schedules:
        # print(f"DEBUG: No schedules found for date {today_iso}")
        return

    for doc in schedules:
        data = doc.to_dict()
        tasks = data.get('tasks', [])
        elder_id = data.get('userId') or data.get('uid') or doc.id
        updated = False
        
        # 0. Fetch Elder Profile for Tier and FCM Token
        profile_doc = db.collection('elder_profiles').document(elder_id).get()
        if not profile_doc.exists:
            # Fallback for elder_name if profile is missing
            elder_name = elder_id
            tier = 'Tier 1'
            fcm_token = None
        else:
            profile_data = profile_doc.to_dict()
            tier = profile_data.get('prediction_tier', 'Tier 1')
            fcm_token = profile_data.get('fcm_token')
            # Handle explicit None or empty string in name field
            elder_name = profile_data.get('name') or profile_data.get('full_name') or elder_id

        for task in tasks:
            task_name = task.get('task_name') or task.get('taskName') or "task"
            category = task.get('type') or task.get('category') or 'common'
            
            # 1. Filter eligible tasks
            status = task.get('status', 'scheduled')
            if status not in ['scheduled', 'reminder_sent']:
                continue
                
            # Skip if already completed
            if task.get('completed') is True or task.get('isCompleted') is True:
                continue

            # 2. Get Scheduled Time
            scheduled_time_str = task.get('scheduledAt') or task.get('scheduledTime')
            
            sch_dt = None
            if scheduled_time_str:
                try:
                    sch_dt = datetime.fromisoformat(scheduled_time_str)
                except: pass
            else:
                 t_str = task.get('time') or task.get('Time')
                 if t_str:
                    try:
                        time_parts = t_str.split(':')
                        sch_dt = datetime(now.year, now.month, now.day, int(time_parts[0]), int(time_parts[1]))
                    except: pass
            
            if not sch_dt:
                # print(f"DEBUG: Task '{task_name}' for {elder_name} has no valid time. Skipping.")
                continue
                
            # 3. Reminder Logic
            reminder_count = task.get('reminder_count', 0)
            last_reminder_at = task.get('last_reminder_at')
            if last_reminder_at:
                try:
                    last_reminder_dt = datetime.fromisoformat(last_reminder_at)
                except:
                    last_reminder_dt = None
            else:
                last_reminder_dt = None

            # Determine Tier Limits
            max_reminders = 2 if "Tier 1" in tier else 5 if "Tier 2" in tier else 100
            
            # Check if it's time for a reminder
            can_remind = False
            if now >= sch_dt:
                if not last_reminder_dt:
                    can_remind = True
                elif (now - last_reminder_dt).total_seconds() >= 115: # slightly less than 120 for boundary safety
                    if reminder_count < max_reminders:
                        can_remind = True

            if can_remind:
                print(f"🔊 Reminding {elder_name} for '{task_name}' (Tier: {tier}, Count: {reminder_count + 1})")
                
                # Use a generic placeholder or dynamic IP if available
                audio_url = f"http://127.0.0.1:8000/api/audio/{elder_id}/{task.get('id') or task.get('taskId')}"
                
                if fcm_token:
                    sent = send_voice_reminder_notification(fcm_token, task_name, audio_url, category)
                    if not sent:
                        print(f"⚠️ Failed to send FCM for {elder_name}")
                else:
                    print(f"⚠️ No FCM token for {elder_name}. Skipping notification.")
                
                task['reminder_count'] = reminder_count + 1
                task['last_reminder_at'] = now.isoformat()
                task['status'] = 'reminder_sent'
                updated = True

            # 4. Check Forgotten Condition (30 mins after scheduled)
            grace_minutes = task.get('graceMinutes', 30)
            cutoff_time = sch_dt + timedelta(minutes=grace_minutes)
            if now > cutoff_time and status != 'missed':
                print(f"🚨 Marking Task MISSED/FORGOTTEN: {task_name} for {elder_name}")
                
                if fcm_token:
                    f_task_id = task.get('id') or task.get('taskId')
                    f_audio_url = f"http://127.0.0.1:8000/api/audio/{elder_id}/{f_task_id}?forgotten=true"
                    send_voice_reminder_notification(fcm_token, f"Forgotten: {task_name}", f_audio_url, "urgent")

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
                            "category": category,
                            "scheduled_time": scheduled_time_str,
                            "grace_minutes": grace_minutes,
                            "tier": tier,
                            "reminder_count": task.get('reminder_count', 0)
                        },
                        "created_at": datetime.utcnow()
                    })
                except Exception as ex:
                    print(f"Failed to log TASK_MISSED: {ex}")

        # 5. Save updates to Firestore if any task changed
        if updated:
            # Use a transaction to prevent overwriting user-initiated changes (like marking a task as completed)
            transaction = db.transaction()
            
            @firestore.transactional
            def apply_task_updates(transaction, doc_ref, modified_tasks):
                snapshot = doc_ref.get(transaction=transaction)
                if not snapshot.exists:
                    return False
                
                latest_data = snapshot.to_dict()
                latest_tasks = latest_data.get('tasks', [])
                any_merged = False
                
                # Merge our reminder/status updates into the latest task list
                for mod_t in modified_tasks:
                    mod_id = mod_t.get('id') or mod_t.get('taskId')
                    for t in latest_tasks:
                        curr_id = t.get('id') or t.get('taskId')
                        if curr_id == mod_id:
                            # CRITICAL: If the task is now completed in the latest DB state, 
                            # do NOT overwrite it with our 'reminder_sent' or 'missed' status.
                            if t.get('completed') or t.get('isCompleted'):
                                continue
                            
                            # Update reminder count and status if our local version is ahead
                            if mod_t.get('reminder_count', 0) > t.get('reminder_count', 0):
                                t['reminder_count'] = mod_t['reminder_count']
                                t['last_reminder_at'] = mod_t.get('last_reminder_at')
                                t['status'] = mod_t.get('status')
                                any_merged = True
                            
                            if mod_t.get('status') == 'missed' and t.get('status') != 'missed':
                                t['status'] = 'missed'
                                any_merged = True
                            break
                
                if any_merged:
                    transaction.update(doc_ref, {"tasks": latest_tasks})
                return any_merged

            try:
                apply_task_updates(transaction, doc.reference, tasks)
            except Exception as e:
                print(f"Failed to update tasks for {elder_id} safely: {e}")
