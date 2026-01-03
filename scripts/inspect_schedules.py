
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def inspect_schedules():
    print("--- Checking collections ---")
    collections = [c.id for c in db.collections()]
    print(f"Collections: {collections}")
    
    for coll_name in ['schedules', 'daily_schedules']:
        if coll_name in collections:
            print(f"\n--- Data in {coll_name} ---")
            docs = db.collection(coll_name).limit(5).stream()
            for doc in docs:
                print(f"ID: {doc.id} => {doc.to_dict()}")
        else:
            print(f"\nCollection {coll_name} NOT found.")

if __name__ == "__main__":
    inspect_schedules()
