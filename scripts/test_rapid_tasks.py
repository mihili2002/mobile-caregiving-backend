import requests
import json

url = "http://127.0.0.1:5000/api/ai/process_voice_command"

print("=== TEST: Rapid Task Creation (without confirmation) ===\n")

# Task 1
print("1. Say: 'Drink water at 1pm'")
r1 = requests.post(url, json={
    "text": "drink water at 1pm",
    "uid": "test_user",
    "session_id": "test_session"
})
print(f"   AI: {r1.json()['reply']}\n")

# Task 2 (before confirming Task 1) - should AUTO-SAVE Task 1
print("2. Say: 'Jogging at 12pm' (without saying 'yes' first)")
r2 = requests.post(url, json={
    "text": "jogging at 12pm",
    "uid": "test_user",
    "session_id": "test_session"
})
print(f"   AI: {r2.json()['reply']}")
print("Task 1 (Drink water) should be AUTO-SAVED\n")

# Task 3 (before confirming Task 2) - should AUTO-SAVE Task 2
print("3. Say: 'Call daughter at 12:30pm' (without saying 'yes' first)")
r3 = requests.post(url, json={
    "text": "call daughter at 12:30pm",
    "uid": "test_user",
    "session_id": "test_session"
})
print(f"   AI: {r3.json()['reply']}")
print("Task 2 (Jogging) should be AUTO-SAVED\n")

# Confirm Task 3
print("4. Say: 'yes'")
r4 = requests.post(url, json={
    "text": "yes",
    "uid": "test_user",
    "session_id": "test_session"
})
print(f"   AI: {r4.json()['reply']}")
print("Task 3 (Call daughter) should be SAVED\n")

print("\n=== RESULT ===")
print("All 3 tasks should now be in Firestore!")
print("Check your Flutter app to verify.")
