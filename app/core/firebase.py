import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore, auth

_db = None

def init_firebase() -> None:
    """
    Initialize Firebase Admin SDK exactly once.
    Priority:
    1) FIREBASE_CREDENTIALS env var
    2) app/core/firebase_key.json
    """
    global _db

    if firebase_admin._apps:
        if _db is None:
            _db = firestore.client()
        return

    env_path = os.environ.get("FIREBASE_CREDENTIALS")
    if env_path:
        cred_path = Path(env_path)
    else:
        cred_path = Path(__file__).resolve().parent / "firebase_key.json"

    if not cred_path.exists():
        raise RuntimeError(
            f"Firebase credentials not found at: {cred_path}\n"
            "Set FIREBASE_CREDENTIALS or place firebase_key.json in app/core/"
        )

    cred = credentials.Certificate(str(cred_path))
    firebase_admin.initialize_app(cred)
    _db = firestore.client()

    print(f"✅ Firebase initialized using: {cred_path}")

def get_db():
    global _db
    if _db is None:
        init_firebase()
    return _db

def verify_id_token(id_token: str):
    init_firebase()
    return auth.verify_id_token(id_token)
