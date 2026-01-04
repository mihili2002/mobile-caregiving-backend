import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, auth, firestore

_firebase_app = None
_db = None  # private variable to avoid stale imports


def init_firebase() -> None:
    """
    Initialize Firebase Admin SDK once and create Firestore client.

    Priority:
    1) FIREBASE_CREDENTIALS env var (absolute or relative)
    2) project_root/keys/firebase_key.json
    """
    global _firebase_app, _db

    # If already initialized, ensure Firestore client exists
    if firebase_admin._apps:
        if _db is None:
            _db = firestore.client()
        return

    env_path = os.getenv("FIREBASE_CREDENTIALS")

    if env_path:
        cred_path = Path(env_path).expanduser()
        if not cred_path.is_absolute():
            project_root = Path(__file__).resolve().parents[2]
            cred_path = project_root / cred_path
    else:
        project_root = Path(__file__).resolve().parents[2]
        cred_path = project_root / "keys" / "firebase_key.json"

    if not cred_path.exists():
        raise RuntimeError(
            f"Firebase credentials not found at: {cred_path}\n"
            "Set FIREBASE_CREDENTIALS env var or place firebase_key.json correctly."
        )

    cred = credentials.Certificate(str(cred_path))
    _firebase_app = firebase_admin.initialize_app(cred)

    # Create Firestore client
    _db = firestore.client()

    print("✅ Firebase Admin initialized successfully.")


def get_db():
    """
    Always returns a valid Firestore client.
    Fixes the common issue: `from app.core.firebase import db` stays None forever.
    """
    global _db
    if _db is None:
        init_firebase()
    if _db is None:
        raise RuntimeError("Firestore db is None (Firebase not initialized)")
    return _db


def verify_id_token(id_token: str):
    """
    Verify Firebase ID token sent from Flutter (Authorization: Bearer <token>).
    """
    init_firebase()
    return auth.verify_id_token(id_token)
