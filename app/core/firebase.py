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

    # --------------------------------------------------
    # Resolve credentials path SAFELY
    # --------------------------------------------------
    env_path = os.environ.get("FIREBASE_CREDENTIALS")

    if env_path:
        cred_path = Path(env_path)
    else:
        # Default to app/core/firebase_key.json relative to THIS file
        cred_path = Path(__file__).resolve().parent / "firebase_key.json"

    if not cred_path.exists():
        raise RuntimeError(
            f"Firebase credentials not found at: {cred_path}\n"
            "Fix one of the following:\n"
            "1) Set FIREBASE_CREDENTIALS env var to a valid JSON file\n"
            "2) Place firebase_key.json in app/core/\n"
        )

    # --------------------------------------------------
    # Initialize Firebase Admin
    # --------------------------------------------------
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
    print(f"Firebase Admin initialized successfully using: {cred_path}")
"""
Firebase admin initialization and helpers.

This module initializes the Firebase Admin SDK for use in the API.
The frontend authenticates users using Firebase Authentication and
passes Firebase ID tokens to the backend. The backend verifies those
tokens using the Firebase Admin SDK and accesses Firestore securely.
"""






def init_firebase():
    """
    Initialize Firebase Admin SDK if not already initialized.

    Priority:
    1. Use FIREBASE_CREDENTIALS environment variable if set
    2. Fallback to local dev file: app/core/firebase_key.json
    """

    global _firebase_app, db

    # Prevent re-initialization (important for Uvicorn reload)
    if firebase_admin._apps:
        return

    # --------------------------------------------------
    # Resolve credentials path SAFELY
    # --------------------------------------------------
    env_path = os.environ.get("FIREBASE_CREDENTIALS")

    if env_path:
        cred_path = Path(env_path)
    else:
        # Default to app/core/firebase_key.json relative to THIS file
        cred_path = Path(__file__).resolve().parent / "firebase_key.json"

    if not cred_path.exists():
        raise RuntimeError(
            f"Firebase credentials not found at: {cred_path}\n"
            "Fix one of the following:\n"
            "1) Set FIREBASE_CREDENTIALS env var to a valid JSON file\n"
            "2) Place firebase_key.json in app/core/\n"
        )

    # --------------------------------------------------
    # Initialize Firebase Admin
    # --------------------------------------------------
    cred = credentials.Certificate(str(cred_path))
    _firebase_app = firebase_admin.initialize_app(cred)

    # Initialize Firestore client
    db = firestore.client()

    print(f"Firebase Admin initialized successfully using: {cred_path}")
