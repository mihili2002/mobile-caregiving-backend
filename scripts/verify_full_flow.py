import datetime
from datetime import timedelta
import time
import sys
import os

# Init Flask Test Client
from app import app, db
from aggregator_worker import aggregate_and_update_risk
from firebase_admin import firestore

def run_test():
    print("Starting System Verification...")
    
    # 1. Setup Test User
    TEST_UID = "test_user_verify_v1"
    today = datetime.datetime.now().strftime("%d.%m.%Y")
    
    # Clean cleanup
    print(f"Cleaning up test user: {TEST_UID}...")
    db.collection('elder_profiles').document(TEST_UID).set({
        "uid": TEST_UID,
        "name": "Test Elder",
        "age": 75,
        "created_at": datetime.datetime.utcnow().isoformat()
    })
    # Delete today's schedule if exists
    db.collection('schedules').document(f"{TEST_UID}_{today}").delete()
    
    # Delete events
    events = db.collection('task_events').where('uid', '==', TEST_UID).stream()
    for e in events:
        e.reference.delete()
        
    client = app.test_client()
    
    # 2. Add a Past Task (Scheduled 1 Hour Ago)
    print("Step 1: Scheduling a task 60 minutes ago...")
    now = datetime.datetime.now()
    past_time = now - timedelta(minutes=60)
    scheduled_at_iso = past_time.isoformat()
    # Format HH:MM for legacy field
    time_str = past_time.strftime("%H:%M")
    
    res = client.post('/api/schedule/add_task', json={
        "uid": TEST_UID,
        "date": today,
        "task": {
            "task_name": "Test Medication",
            "time": time_str,
            "type": "medication",
            # Injecting explicit scheduledAt to force delay calculation
            # In real app, this is sent by frontend using current date + time selection
            "scheduledTime": scheduled_at_iso, 
            "graceMinutes": 30
        }
    })
    
    if res.status_code != 200:
        print(f"Failed to add task: {res.json}")
        return
        
    task_id = res.json['task']['taskId']
    print(f"   -> Task Created. ID: {task_id}")
    
    # 3. Complete the Task NOW (Creating ~60min delay)
    print("Step 2: Completing task NOW (generating delay)...")
    res = client.post('/api/schedule/complete', json={
        "uid": TEST_UID,
        "date": today,
        "taskId": task_id
    })
    
    if res.status_code != 200:
        print(f"Failed to complete task: {res.json}")
        return
        
    print(f"   -> Task Completed. Timestamp: {res.json['completedAt']}")
    
    # 4. Verify Event Log
    print("Step 3: Verifying Event Log...")
    events = list(db.collection('task_events')\
        .where('uid', '==', TEST_UID)\
        .where('type', '==', 'TASK_COMPLETED')\
        .stream())
        
    if not events:
        print("No TASK_COMPLETED event found!")
        return
        
    ev_data = events[0].to_dict()
    delay = ev_data['meta'].get('delay_minutes', 0)
    print(f"   -> Event Found! Recorded Delay: {delay} minutes")
    
    if delay < 58: # approximate check
        print("Warning: Delay calculation seems off. Expected ~60.")
        
    # 5. Run Aggregator (Manually Trigger)
    print("Step 4: Running Weekly Aggregator...")
    try:
        aggregate_and_update_risk()
    except Exception as e:
        print(f"Aggregator failed: {e}")
        return
        
    # 6. Check Risk Profile
    print("Step 5: Verifying Elder Profile update...")
    profile = db.collection('elder_profiles').document(TEST_UID).get()
    p_data = profile.to_dict()
    
    print("\n--- TEST RESULTS ---")
    print(f"Elder UID: {TEST_UID}")
    print(f"Avg Delay (Last 7 Days): {p_data.get('avg_task_delay_min')} min")
    print(f"Prediction Probability: {p_data.get('prediction_probability')}")
    print(f"Prediction Tier: {p_data.get('prediction_tier')}")
    print(f"Tier Reason: {p_data.get('tier_reason_summary')}")
    print("-----------------------")
    
    if p_data.get('avg_task_delay_min') > 0:
        print("SUCCESS: System correctly logged behavior, aggregated stats, and updated risk!")
    else:
        print("FAILURE: Stats did not update correctly.")

if __name__ == "__main__":
    run_test()
