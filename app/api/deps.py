"""
API dependencies (e.g., Firebase auth verification).

Provides FastAPI dependencies to verify Firebase ID tokens.
"""

from typing import List, Callable

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth

# 🔐 FastAPI security scheme (this fixes Swagger + header binding)
security = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Verify Firebase ID token from Authorization header.

    Expects:
        Authorization: Bearer <id_token>
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
    Return a FastAPI dependency that enforces a user's role.

    The Firebase ID token is expected to have a custom claim `role`.
    Example claims:
        {'role': 'patient'}
        {'role': 'doctor'}
    """

    def _checker(user=Depends(get_current_user)):
        role = user.get("role") or user.get("roles")

        if isinstance(role, list):
            is_allowed = any(r in allowed for r in role)
        else:
            is_allowed = role in allowed

        if not is_allowed:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions",
            )

        return user

    return _checker
