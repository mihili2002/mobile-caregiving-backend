
import firebase_admin
from firebase_admin import credentials, firestore
import os

# Initialize Firebase Admin
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def list_users():
    print("--- Listing Users ---")
    users_ref = db.collection('users')
    docs = users_ref.stream()
    
    found_caregiver = False
    for doc in docs:
        data = doc.to_dict()
        print(f"ID: {doc.id}, Role: {data.get('role', 'N/A')}, Name: {data.get('name', 'N/A')}")
        if data.get('role') == 'caregiver':
            found_caregiver = True
            
    if not found_caregiver:
        print("\nWARNING: No user with role 'caregiver' found!")

if __name__ == "__main__":
    list_users()
