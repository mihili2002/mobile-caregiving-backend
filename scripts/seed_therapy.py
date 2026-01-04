
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Using the same test UID as before
TEST_UID = "T9bcdMiMEfRxfvihEQN3KcqskCi1" 

therapy_data = [
    {
        "elder_id": TEST_UID,
        "activity_name": "Morning Stretch",
        "duration": "15 mins",
        "instructions": "Gentle arm and neck stretches. Do not overexert.",
        "is_active": True
    },
    {
        "elder_id": TEST_UID,
        "activity_name": "Walking Practice",
        "duration": "20 mins",
        "instructions": "Walk in the hallway with support.",
        "is_active": True
    },
    {
        "elder_id": TEST_UID,
        "activity_name": "Cognitive Puzzle",
        "duration": "10 mins",
        "instructions": "Complete one Sudoku or Crossword.",
        "is_active": True
    }
]

def seed_therapy():
    collection = db.collection('therapy_assignments')
    for t in therapy_data:
        collection.add(t)
        print(f"Added {t['activity_name']}")

if __name__ == "__main__":
    seed_therapy()
