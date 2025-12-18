"""Health records routes."""
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user

router = APIRouter(prefix="/health_records", tags=["health_records"])


@router.get("/")
async def list_records(user=Depends(get_current_user)):
    return {"items": []}
