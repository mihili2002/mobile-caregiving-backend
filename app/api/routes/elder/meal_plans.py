from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from google.cloud.firestore_v1.base_query import FieldFilter
from app.api.deps import require_role
from app.core.firebase import get_db

router = APIRouter(prefix="/elder/meal-plans", tags=["elder_meal_plans"])


@router.get("/dashboard")
async def elder_meal_plan_dashboard(user=Depends(require_role(["elder"]))):
    elder_id = user["uid"]

    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore client not initialized")

    # -------------------------
    # Current approved plan
    # -------------------------
    current_docs = (
        db.collection("meal_plans")
        .where(filter=FieldFilter("elder_id", "==", elder_id))
        .where(filter=FieldFilter("status", "==", "approved"))
        .order_by("start_date", direction="DESCENDING")
        .limit(1)
        .stream()
    )

    current = [{"id": d.id, **(d.to_dict() or {})} for d in current_docs]
    current_plan = current[0] if current else None

    # -------------------------
    # Completed plans
    # -------------------------
    completed_docs = (
        db.collection("meal_plans")
        .where(filter=FieldFilter("elder_id", "==", elder_id))
        .where(filter=FieldFilter("status", "==", "completed"))
        .order_by("end_date", direction="DESCENDING")
        .stream()
    )

    completed = [{"id": d.id, **(d.to_dict() or {})} for d in completed_docs]

    # -------------------------
    # All submissions
    # -------------------------
    submission_docs = (
        db.collection("elder_health_submissions")
        .where("elder_id", "==", elder_id)
        .order_by("submitted_at", direction="DESCENDING")
        .stream()
    )

    submissions = []
    reviewer_ids = set()

    for d in submission_docs:
        data = d.to_dict() or {}
        reviewer_id = data.get("reviewed_by")

        if reviewer_id:
            reviewer_ids.add(reviewer_id)

        submissions.append(
            {
                "id": d.id,
                "submitted_at": data.get("submitted_at"),
                "reviewed_at": data.get("reviewed_at"),
                "reviewed_by": reviewer_id,  # temp store ID
                "status": data.get("status"),
            }
        )

    # -------------------------
    # Fetch reviewer names
    # -------------------------
    reviewer_map = {}

    if reviewer_ids:
        user_refs = [
            db.collection("users").document(uid)
            for uid in reviewer_ids
        ]

    user_docs = db.collection("users").where(
        filter=FieldFilter("__name__", "in", user_refs)
    ).stream()

    for u in user_docs:
        user_data = u.to_dict() or {}
        reviewer_map[u.id] = user_data.get("name", "Unknown")

    # -------------------------
    # Replace IDs with names
    # -------------------------
    for submission in submissions:
        reviewer_id = submission["reviewed_by"]
        submission["reviewed_by"] = (
            reviewer_map.get(reviewer_id) if reviewer_id else None
        )

    return {
        "current_meal_plan": current_plan,
        "completed_meal_plans": completed,
        "all_submissions": submissions,
    }


@router.get("/{meal_plan_id}")
async def get_meal_plan(meal_plan_id: str, user=Depends(require_role(["elder"]))):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore client not initialized")

    doc = db.collection("meal_plans").document(meal_plan_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Meal plan not found")

    data = doc.to_dict() or {}
    if data.get("elder_id") != user["uid"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    return {"id": doc.id, **data}


@router.get("/by-submission/{submission_id}")
async def get_meal_plan_by_submission(
    submission_id: str,
    user=Depends(require_role(["elder"]))
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore client not initialized")

    docs = (
        db.collection("meal_plans")
        .where("health_submission_id", "==", submission_id)
        .limit(1)
        .stream()
    )

    for d in docs:
        data = d.to_dict() or {}

        # Extra security: elders can only fetch their own meal plan
        if data.get("elder_id") != user["uid"]:
            raise HTTPException(status_code=403, detail="Unauthorized")

        return {"meal_plan_id": d.id}

    raise HTTPException(status_code=404, detail="Meal plan not found")
