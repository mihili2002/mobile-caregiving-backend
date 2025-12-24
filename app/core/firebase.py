"""
Firebase admin initialization and helpers.

This module initializes the Firebase Admin SDK for use in the API.
The frontend authenticates users using Firebase Authentication and
passes Firebase ID tokens to the backend. The backend verifies those
tokens using the Firebase Admin SDK and accesses Firestore securely.
"""

import os
import firebase_admin
from firebase_admin import credentials, auth, firestore

# Global references to avoid re-initialization
_firebase_app = None
db = None


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

    # Try environment variable first
    cred_path = os.environ.get(
        "FIREBASE_CREDENTIALS",
        "app/core/firebase_key.json"
    )

    if not os.path.exists(cred_path):
        raise RuntimeError(
            f"Firebase credentials not found at: {cred_path}\n"
            "Set FIREBASE_CREDENTIALS env var or place firebase_key.json correctly."
        )

    # Initialize Firebase Admin
    cred = credentials.Certificate(cred_path)
    _firebase_app = firebase_admin.initialize_app(cred)

    # Initialize Firestore client
    db = firestore.client()

    print("Firebase Admin initialized successfully.")
