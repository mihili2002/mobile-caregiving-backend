"""API dependencies (e.g., Firebase auth verification).

Provides FastAPI dependencies to verify Firebase ID tokens.
"""
from fastapi import Depends, HTTPException, Header
from firebase_admin import auth
from firebase_admin.auth import InvalidIdTokenError


async def get_current_user(authorization: str | None = Header(None)):
    """Verify Firebase ID token from Authorization header and return decoded token.

    Expects header: Authorization: Bearer <id_token>
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    id_token = parts[1]
    try:
        decoded = auth.verify_id_token(id_token)
        return decoded
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid ID token") from exc
