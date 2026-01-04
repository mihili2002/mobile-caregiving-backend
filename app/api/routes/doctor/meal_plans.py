from fastapi import APIRouter, Depends, Body, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timezone, date, timedelta

from app.api.deps import require_role
from app.core import firebase
from app.services.meal_plan_pipeline import build_meal_plan
from app.models.meal_plan import MealPlan

router = APIRouter(prefix="/doctor/meal-plans", tags=["doctor_meal_plans"])


@router.post("/generate", status_code=201)
async def generate_meal_plan(
    elder_id: str = Body(...),
    health_submission_id: Optional[str] = Body(None),
    user=Depends(require_role(["doctor"]))
):
    # 1. Load health submission (latest pending if not provided)
    if health_submission_id:
        submission_doc = firebase.db.collection("elder_health_submissions").document(health_submission_id).get()
        if not submission_doc.exists:
            raise HTTPException(status_code=404, detail="Submission not found")
        submission = submission_doc.to_dict()
    else:
        docs = (
            firebase.db.collection("elder_health_submissions")
            .where("elder_id", "==", elder_id)
            .where("status", "==", "pending")
            .order_by("submitted_at", direction="DESCENDING")
            .limit(1)
            .stream()
        )
        items = [{"id": d.id, **d.to_dict()} for d in docs]
        if not items:
            raise HTTPException(status_code=404, detail="No pending submission found")
        submission = items[0]
        health_submission_id = submission["id"]

    # 2. Build meal plan using pipeline (ML / AI)
    try:
        generated = build_meal_plan(submission)  # your pipeline can adapt to submission dict
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Meal plan generation failed: {e}")

    # 3. Save MealPlan doc
    start_date = date.today()
    end_date = start_date + timedelta(days=6)

    meal_plan_doc = {
    "elder_id": elder_id,
    "created_at": datetime.now(timezone.utc),
    "health_submission_id": health_submission_id,
    "start_date": start_date.isoformat(),
    "end_date": end_date.isoformat(),
    "status": "pending",

    "days": generated.get("weekly_meal_plan", {}).get("week", []),

    "dietitian_notes": generated.get("weekly_meal_plan", {}).get("dietitian_notes"),
    "nutrient_targets": generated.get("nutrient_targets"),
    "warnings": generated.get("warnings"),
    }


    new_ref = firebase.db.collection("meal_plans").document()
    new_ref.set(meal_plan_doc)

    # 4. update submission -> approved/reviewed state optional
    firebase.db.collection("elder_health_submissions").document(health_submission_id).update({
        "status": "approved",
        "reviewed_by": user["uid"],
        "reviewed_at": datetime.now(timezone.utc),
    })

    return {"id": new_ref.id, **meal_plan_doc}


@router.post("/{meal_plan_id}/approve")
async def approve_meal_plan(meal_plan_id: str, user=Depends(require_role(["doctor"]))):
    ref = firebase.db.collection("meal_plans").document(meal_plan_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Meal plan not found")

    ref.update({
        "status": "approved",
        "approved_by": user["uid"],
        "approved_at": datetime.now(timezone.utc),
    })
    return {"message": "Meal plan approved"}


@router.post("/{meal_plan_id}/reject")
async def reject_meal_plan(
    meal_plan_id: str,
    doctor_feedback: Optional[str] = Body(None),
    user=Depends(require_role(["doctor"]))
):
    ref = firebase.db.collection("meal_plans").document(meal_plan_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Meal plan not found")

    ref.update({
        "status": "rejected",
        "rejected_by": user["uid"],
        "rejected_at": datetime.now(timezone.utc),
        "doctor_feedback": doctor_feedback,
    })
    return {"message": "Meal plan rejected"}


@router.put("/{meal_plan_id}")
async def edit_meal_plan(
    meal_plan_id: str,
    updates: Dict[str, Any] = Body(...),
    user=Depends(require_role(["doctor"]))
):
    ref = firebase.db.collection("meal_plans").document(meal_plan_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Meal plan not found")

    # Only allow editing if not completed
    current = doc.to_dict()
    if current.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Cannot edit completed meal plan")

    allowed_fields = {"days", "status", "doctor_feedback", "start_date", "end_date"}
    safe_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    safe_updates["updated_at"] = datetime.now(timezone.utc)
    safe_updates["updated_by"] = user["uid"]

    ref.update(safe_updates)
    return {"message": "Meal plan updated", "updates": safe_updates}