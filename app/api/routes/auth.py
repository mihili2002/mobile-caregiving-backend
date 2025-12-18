"""Authentication-related routes.

Frontend performs authentication with Firebase; backend exposes helper
endpoints and token verification status.
"""
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    return {"uid": user.get("uid"), "email": user.get("email")}
