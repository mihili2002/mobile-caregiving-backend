"""
API dependencies (Firebase auth + role verification via Firestore).
"""

from typing import List, Callable

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth, firestore

# Security scheme
security = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Verify Firebase ID token and return decoded token.
    """
    try:
        id_token = credentials.credentials
        decoded = auth.verify_id_token(id_token)
        return decoded

    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid ID token",
        ) from exc


def require_role(allowed: List[str]) -> Callable:
    """
    Enforce role-based access using Firestore users collection.
    """

    def _checker(user=Depends(get_current_user)):
        uid = user.get("uid")

        if not uid:
            raise HTTPException(status_code=401, detail="Invalid user token")

        # 🔹 Fetch role from Firestore
        db = firestore.client()
        doc = db.collection("users").document(uid).get()

        if not doc.exists:
            raise HTTPException(status_code=403, detail="User record not found")

        role = doc.get("role")

        print("DEBUG uid:", uid)
        print("DEBUG role:", role)

        if role not in allowed:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions",
            )

        return user

    return _checker
