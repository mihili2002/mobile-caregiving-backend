import requests
import json

url = "http://127.0.0.1:8000/api/ai/process_voice_command"

# Test 1: Create a task (should ask for confirmation)
print("=== TEST 1: Task Creation (should ask for confirmation) ===")
response1 = requests.post(url, json={
    "text": "remind me to drink water at 3pm",
    "uid": "test_user",
    "session_id": "test_session_123"
})
print(f"Status: {response1.status_code}")
print(f"Response: {response1.json()}")
print()

# Test 2: Confirm with "yes" (should save task)
print("=== TEST 2: Confirm with 'yes' (should save task) ===")
response2 = requests.post(url, json={
    "text": "yes",
    "uid": "test_user",
    "session_id": "test_session_123"
})
print(f"Status: {response2.status_code}")
print(f"Response: {response2.json()}")
print()

# Test 3: Create another task
print("=== TEST 3: Another task (should ask for confirmation) ===")
response3 = requests.post(url, json={
    "text": "dicti",
    "uid": "test_user",
    "session_id": "test_session_456"
})
print(f"Status: {response3.status_code}")
print(f"Response: {response3.json()}")
print()

# Test 4: Reject with "no" (should discard)
print("=== TEST 4: Reject with 'no' (should discard) ===")
response4 = requests.post(url, json={
    "text": "no",
    "uid": "test_user",
    "session_id": "test_session_456"
})
print(f"Status: {response4.status_code}")
print(f"Response: {response4.json()}")
