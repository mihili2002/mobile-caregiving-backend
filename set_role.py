import firebase_admin
from firebase_admin import credentials, auth
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SERVICE_ACCOUNT_PATH = PROJECT_ROOT / "app" / "core" / "firebase_key.json"

if not firebase_admin._apps:
    cred = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))
    firebase_admin.initialize_app(cred)

uid = "TObG6senS8dDgnladZ8v0vjqWv33"
auth.set_custom_user_claims(uid, {"role": "elder"})

print(f"✅ Role claim set successfully for UID: {uid}")
print("✅ Now log out and log in again OR refresh token using getIdToken(true)")
