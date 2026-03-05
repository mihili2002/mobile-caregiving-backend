import firebase_admin
from firebase_admin import credentials, firestore, messaging
import sys
import os

# Init Firebase
try:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)
except:
    pass

db = firestore.client()

def test_voice_reminder_flow(uid, task_name, category):
    print(f"🚀 Testing voice reminder flow for user: {uid}")
    
    # 1. Fetch FCM Token
    doc = db.collection('elder_profiles').document(uid).get()
    if not doc.exists:
        print(f"❌ User {uid} not found.")
        return
    
    data = doc.to_dict()
    fcm_token = data.get('fcm_token')
    tier = data.get('prediction_tier', 'Tier 1')
    
    if not fcm_token:
        print(f"❌ No fcm_token found for {uid}. Cannot send notification.")
        return

    print(f"✅ Found FCM token and Tier: {tier}")
    
    # 2. Simulate notification send
    audio_url = f"https://your-api.com/api/audio/{uid}/test_task"
    
    print(f"Sending notification for: {task_name} ({category})")
    message = messaging.Message(
        data={
            "type": "VOICE_REMINDER",
            "taskName": task_name,
            "audioUrl": audio_url,
            "category": category,
        },
        token=fcm_token,
    )
    
    try:
        response = messaging.send(message)
        print(f"✅ Message sent successfully: {response}")
    except Exception as e:
        print(f"❌ Error sending message: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_voice_flow.py <uid>")
        sys.exit(1)
        
    uid = sys.argv[1]
    test_voice_reminder_flow(uid, "Take Heart Medicine", "health")
