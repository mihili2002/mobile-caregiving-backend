import requests
import json
import uuid

BASE_URL = "http://localhost:8000"  # Adjust if server port is different
UID = "ebony_elder_1"
SESSION_ID = f"test_{uuid.uuid4().hex[:8]}"

def test_greeting():
    print("\n--- Testing Dynamic Greeting ---")
    url = f"{BASE_URL}/api/ai/greet?uid={UID}"
    try:
        response = requests.get(url)
        print(f"Status: {response.statusCode if hasattr(response, 'statusCode') else response.status_code}")
        data = response.json()
        print(f"Alex: {data['reply']}")
    except Exception as e:
        print(f"Error: {e}")

def test_conversation():
    print("\n--- Testing Multi-turn Conversation ---")
    url = f"{BASE_URL}/api/ai/process_voice_command"
    
    # Turn 1: Hello
    print("User: hello")
    payload = {"text": "hello", "uid": UID, "session_id": SESSION_ID}
    res1 = requests.post(url, json=payload).json()
    print(f"Alex: {res1['reply']}")
    
    # Turn 2: Follow up
    print("\nUser: what can you do for me?")
    payload = {"text": "what can you do for me?", "uid": UID, "session_id": SESSION_ID}
    res2 = requests.post(url, json=payload).json()
    print(f"Alex: {res2['reply']}")

    # Turn 3: Contextual task
    print("\nUser: remind me to take my medicine in 1 hour")
    payload = {"text": "remind me to take my medicine in 1 hour", "uid": UID, "session_id": SESSION_ID}
    res3 = requests.post(url, json=payload).json()
    print(f"Alex: {res3['reply']}")
    if res3.get('is_confirmation'):
        print(f"DEBUG: Task Detected: {res3.get('task')}")

if __name__ == "__main__":
    # Ensure server is running before this
    test_greeting()
    # test_conversation() # Commented out as it needs the server instance
