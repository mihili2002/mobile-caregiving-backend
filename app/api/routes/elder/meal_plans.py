from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from datetime import datetime, timezone

from app.api.deps import require_role
from app.core import firebase

router = APIRouter(prefix="/elder/meal-plans", tags=["elder_meal_plans"])


@router.get("/dashboard")
async def elder_meal_plan_dashboard(user=Depends(require_role(["elder"]))):
    elder_id = user["uid"]

    # Current approved plan (not completed)
    current_docs = (
        firebase.db.collection("meal_plans")
        .where("elder_id", "==", elder_id)
        .where("status", "==", "approved")
        .order_by("start_date", direction="DESCENDING")
        .limit(1)
        .stream()
    )
    current = [{"id": d.id, **d.to_dict()} for d in current_docs]
    current_plan = current[0] if current else None

    # Completed plans list
    completed_docs = (
        firebase.db.collection("meal_plans")
        .where("elder_id", "==", elder_id)
        .where("status", "==", "completed")
        .order_by("end_date", direction="DESCENDING")
        .stream()
    )
    completed = [{"id": d.id, **d.to_dict()} for d in completed_docs]

    return {
        "current_meal_plan": current_plan,
        "completed_meal_plans": completed,
    }


@router.get("/{meal_plan_id}")
async def get_meal_plan(meal_plan_id: str, user=Depends(require_role(["elder"]))):
    doc = firebase.db.collection("meal_plans").document(meal_plan_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Meal plan not found")

    data = doc.to_dict()
    if data.get("elder_id") != user["uid"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    return {"id": doc.id, **data}
