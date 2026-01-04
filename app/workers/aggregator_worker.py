
import threading
import time
from datetime import datetime, timedelta
from firebase_admin import firestore
import traceback
from google.cloud.firestore import FieldFilter, And
from app.services.ml_inference import predict_elder_risk

def start_aggregator():
    thread = threading.Thread(target=_run_aggregator, daemon=True)
    thread.start()

def _run_aggregator():
    # print("Aggregator Worker Started. Running daily aggregation...")
    while True:
        try:
            aggregate_and_update_risk()
        except Exception as e:
            print(f"Error in aggregator job: {e}")
            traceback.print_exc()
        
        # Run every 24 hours
        time.sleep(86400)

def aggregate_and_update_risk():
    db = firestore.client()
    # print("Running aggregation for all elders...")
    
    # 1. Get all Elder Profiles
    elders_ref = db.collection('elder_profiles').stream()
    
    # Time Windows
    now = datetime.utcnow()
    cutoff_7_days = now - timedelta(days=7)
    
    # Generates list of last 7 date strings (YYYY-MM-DD)
    dates_to_check = []
    for i in range(7):
        d = now - timedelta(days=i)
        dates_to_check.append(d.strftime("%Y-%m-%d"))
    
    for doc in elders_ref:
        data = doc.to_dict()
        uid = data.get('uid')
        if not uid: continue
        
        # print(f"Aggregating for Elder: {uid}")
        
        try:
            # === A & B & C: Missed & Delays (From Schedules) ===
            missed_tasks_count = 0
            missed_meds_count = 0
            total_delay_minutes = 0
            completed_tasks_count = 0
            
            # Fetch last 7 schedule docs
            schedules = db.collection('schedules')\
                .where(filter=And(filters=[
                    FieldFilter('uid', '==', uid),
                    FieldFilter('date', 'in', dates_to_check)
                ]))\
                .stream()
            
            for sched in schedules:
                s_data = sched.to_dict()
                tasks = s_data.get('tasks', [])
                date_str = s_data.get('date') # YYYY-MM-DD
                
                for t in tasks:
                    status = t.get('status', 'scheduled')
                    t_type = t.get('type') or t.get('category') or 'common'
                    
                    # Missed
                    if status == 'missed':
                        missed_tasks_count += 1
                        if t_type == 'medication':
                            missed_meds_count += 1
                    
                    # Completed -> Delay
                    # Check explicit boolean or status
                    is_completed = t.get('completed') is True or status == 'completed'
                    if is_completed:
                        completed_at_iso = t.get('completedAt')
                        
                        # Determine Scheduled Time
                        scheduled_dt = None
                        if t.get('scheduledAt'):
                            try:
                                scheduled_dt = datetime.fromisoformat(t.get('scheduledAt'))
                            except: pass
                        elif t.get('time') and date_str:
                            try:
                                parts = t['time'].split(':') # HH:MM
                                day_parts = date_str.split('-') # YYYY-MM-DD
                                scheduled_dt = datetime(
                                    int(day_parts[0]), int(day_parts[1]), int(day_parts[2]), 
                                    int(parts[0]), int(parts[1])
                                )
                            except: pass
                            
                        if completed_at_iso and scheduled_dt:
                            try:
                                comp_dt = datetime.fromisoformat(completed_at_iso)
                                # Naive comparison (assume both local or both UTC-ish enough for diff)
                                # Best: normalize to UTC. App sends ISO 8601.
                                
                                # Remove tzinfo for simple diff if mixed
                                if comp_dt.tzinfo and not scheduled_dt.tzinfo:
                                    comp_dt = comp_dt.replace(tzinfo=None)
                                if not comp_dt.tzinfo and scheduled_dt.tzinfo:
                                    scheduled_dt = scheduled_dt.replace(tzinfo=None)
                                    
                                delay = (comp_dt - scheduled_dt).total_seconds() / 60.0
                                delay = max(0, delay) # No negative delay (early is 0 delay)
                                
                                total_delay_minutes += min(int(delay), 120) # Cap at 120
                                completed_tasks_count += 1
                            except:
                                pass

            avg_delay = (total_delay_minutes / completed_tasks_count) if completed_tasks_count > 0 else 0
            
            # === D: Snoozes (From Events) ===
            snooze_count = 0
            # Fallback for index issues: Query events via Python filter if needed, 
            # but 'uid' + 'at' range is standard.
            try:
                # filters
                f1 = FieldFilter('uid', '==', uid)
                f2 = FieldFilter('type', '==', 'REMINDER_SNOOZED')
                f3 = FieldFilter('at', '>=', cutoff_7_days.isoformat())
                
                events = db.collection('task_events')\
                    .where(filter=And(filters=[f1, f2, f3]))\
                    .stream()
                for _ in events:
                    snooze_count += 1
            except Exception as e:
                # print(f"Snooze query error (likely index missing). Assuming 0.")
                pass
            
            snoozes_per_day = snooze_count / 7.0
            snoozes_per_day = min(snoozes_per_day, 10.0)

            # print(f"  -> Missed: {missed_tasks_count}, Meds: {missed_meds_count}, Delay: {avg_delay:.1f}, Snoozes: {snoozes_per_day:.1f}")

            # 4. Prepare Updates
            updates = {
                "missed_tasks_per_week": int(missed_tasks_count),
                "missed_meds_per_week": int(missed_meds_count),
                "avg_task_delay_min": round(avg_delay, 1),
                "snoozes_per_day": round(snoozes_per_day, 1)
            }
            
            # 5. Re-Run Prediction
            prediction_input = data.copy()
            prediction_input.update(updates)
            
            risk_result = predict_elder_risk(prediction_input)
            
            updates.update(risk_result)
            updates["prediction_updated_at"] = datetime.utcnow().isoformat()
            
            # 6. Save
            db.collection('elder_profiles').document(uid).update(updates)
            # print(f"  -> Updated Profile: {risk_result}")
            
        except Exception as ex:
            print(f"Error aggregating for {uid}: {ex}")
            traceback.print_exc()
