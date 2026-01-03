
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Hardcoded UID from verify script output or logs, or just a known one
TEST_UID = "T9bcdMiMEfRxfvihEQN3KcqskCi1" 

meds = [
    {
        "drug_name": "Metformin",
        "dosage": "500mg",
        "frequency": "1-0-1",
        "timing": "after_meal",
        "status": "active",
        "elder_id": TEST_UID,
        "created_at": datetime.utcnow().isoformat()
    },
    {
        "drug_name": "Aspirin",
        "dosage": "75mg",
        "frequency": "0-0-1",
        "timing": "after_meal",
        "status": "active",
        "elder_id": TEST_UID,
        "created_at": datetime.utcnow().isoformat()
    }
]

def seed_meds():
    collection = db.collection('patient_medications')
    for m in meds:
        collection.add(m)
        print(f"Added {m['drug_name']}")

if __name__ == "__main__":
    seed_meds()
