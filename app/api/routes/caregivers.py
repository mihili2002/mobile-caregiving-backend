"""Caregiver-related API routes."""
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user

router = APIRouter(prefix="/caregivers", tags=["caregivers"])


@router.get("/")
async def list_caregivers(user=Depends(get_current_user)):
    return {"items": []}
