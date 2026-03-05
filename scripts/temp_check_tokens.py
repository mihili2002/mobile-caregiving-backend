
import os
import firebase_admin
from firebase_admin import credentials, firestore

# Setup Firebase
cred_path = r"D:\Users\ASUS\Desktop\Project Backend\mobile-caregiving-backend\app\core\firebase_key.json"

cred = credentials.Certificate(cred_path)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

def check_tokens():
    print("--- Searching for any profile with fcm_token ---")
    profiles = db.collection('elder_profiles').stream()
    
    found = False
    for doc in profiles:
        data = doc.to_dict()
        if 'fcm_token' in data and data['fcm_token']:
            found = True
            print(f"✅ FOUND TOKEN for {doc.id}: {data['fcm_token'][:20]}...")
            
    if not found:
        print("❌ No profiles found with an fcm_token.")

if __name__ == "__main__":
    check_tokens()
