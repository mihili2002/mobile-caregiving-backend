
import firebase_admin
from firebase_admin import credentials, firestore
import sys

# Initialize Firebase (reuses existing credentials if possible)
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
except ValueError:
    pass # Already initialized

db = firestore.client()

def set_tier(tier_level):
    print("Fetching elders...")
    elders_ref = db.collection('elder_profiles').stream()
    
    tier_str = "Tier 1"
    prob = 0.1
    
    if tier_level == 2:
        tier_str = "Tier 2"
        prob = 0.5
    elif tier_level == 3:
        tier_str = "Tier 3"
        prob = 0.9

    updated_count = 0
    for doc in elders_ref:
        uid = doc.id
        print(f"Updating {uid} to {tier_str}...")
        
        db.collection('elder_profiles').document(uid).update({
            "prediction_tier": f"{tier_str} (Manual Override)",
            "prediction_probability": prob,
            "tier_reason_summary": "Manual Test Override"
        })
        updated_count += 1

    print(f"Successfully updated {updated_count} profiles to {tier_str}.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python set_risk_tier.py <1|2|3>")
        sys.exit(1)
        
    try:
        level = int(sys.argv[1])
        if level not in [1, 2, 3]:
            raise ValueError
        set_tier(level)
    except ValueError:
        print("Invalid Tier. Please use 1, 2, or 3.")
