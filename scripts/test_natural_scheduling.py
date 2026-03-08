import requests
import json
import uuid

BASE_URL = "http://127.0.0.1:8000"
UID = "test_elder_123"
SESSION_ID = f"session_{uuid.uuid4().hex[:8]}"

def talk(text):
    print(f"\n[Elder]: {text}")
    res = requests.post(
        f"{BASE_URL}/api/ai/process_voice_command",
        json={"text": text, "uid": UID, "session_id": SESSION_ID}
    )
    data = res.json()
    reply = data.get("reply")
    is_conf = data.get("is_confirmation", False)
    print(f"[Alex]: {reply}")
    if is_conf:
        print(f"DEBUG: Task Preview: {data.get('task')}")
    return data

def test_multi_turn_scheduling():
    print(f"--- STARTING NATURAL SCHEDULING TEST (Session: {SESSION_ID}) ---")
    
    # 1. Multi-turn slot filling
    talk("Alex, I would like to add watering my plants every morning.")
    talk("At 9:00 AM, after breakfast.")
    talk("yes") # Confirmation
    
    # 2. Daily frequency and Proactive reminder
    talk("Remind me to take my evening medicine at 8:30 PM every day.")
    talk("yes") # Confirmation for the task
    
    # 3. Future date (Friday) and Proactive reminder
    talk("Please add my doctor's appointment this Friday at 3:00 PM.")
    # Expect Alex to offer a reminder
    talk("Yes, that would be helpful.") # Confirmation for the reminder offer
    talk("yes") # Confirmation for the saving
    
    print("\n--- TEST COMPLETE ---")

if __name__ == "__main__":
    try:
        test_multi_turn_scheduling()
    except Exception as e:
        print(f"Error: {e}")
