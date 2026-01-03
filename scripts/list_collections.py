
import firebase_admin
from firebase_admin import credentials, firestore
import os

# Initialize Firebase (Check if already initialized to avoid errors if imported)
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def list_all_collections():
    print("\n========= FIRESTORE COLLECTIONS =========")
    collections = db.collections()
    found_any = False
    
    for coll in collections:
        found_any = True
        print(f"\n📂 Collection: {coll.id}")
        
        # Get count (approx method by getting stream)
        docs = list(coll.limit(5).stream())
        if not docs:
            print("   (Empty)")
            continue
            
        print(f"   Sample Documents ({len(docs)} shown):")
        for doc in docs:
            # Print ID and a abbreviated dict
            data = doc.to_dict()
            keys = list(data.keys())[:3] # Show first 3 keys
            preview = {k: data[k] for k in keys}
            print(f"   - {doc.id}: {preview}...")
            
    if not found_any:
        print("\n(No collections found in this project)")
    print("\n=========================================")

if __name__ == "__main__":
    list_all_collections()
