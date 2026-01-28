from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List

from app.api.deps import require_role
from app.core.firebase import get_db

router = APIRouter(prefix="/doctor/dashboard", tags=["doctor_dashboard"])


@router.get("/")
async def doctor_dashboard(user=Depends(require_role(["doctor"]))):
    """
    Doctor dashboard:
    - Fetch latest health submission per elder
    - Approval comes from THAT submission
    - Meal plan is fetched ONLY for THAT submission
    """
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore client not initialized")

    # 1️⃣ Fetch all health submissions
    submissions = db.collection("elder_health_submissions").stream()

    # 2️⃣ Keep latest submission per elder
    latest_map: Dict[str, Dict[str, Any]] = {}

    for doc in submissions:
        data = doc.to_dict() or {}
        elder_id = data.get("elder_id")
        submitted_at = data.get("submitted_at")

        if not elder_id or not submitted_at:
            continue

        prev = latest_map.get(elder_id)

        if prev is None or submitted_at > prev.get("submitted_at"):
            latest_map[elder_id] = {
                "id": doc.id,
                **data,
            }

    rows: List[Dict[str, Any]] = []

    # 3️⃣ Attach meal plan ONLY for the latest submission
    for elder_id, latest_submission in latest_map.items():
        submission_id = latest_submission["id"]

        meal_docs = (
            db.collection("meal_plans")
            .where("health_submission_id", "==", submission_id)
            .limit(1)
            .stream()
        )

        meal_items = [{"id": d.id, **(d.to_dict() or {})} for d in meal_docs]
        latest_meal_plan = meal_items[0] if meal_items else None

        rows.append({
            "elder_id": elder_id,
            "elder_name": None,  # frontend-safe, unchanged
            "latest_submission": {
                **latest_submission,
                "approved": latest_submission.get("approved", False),
            },
            "latest_meal_plan": latest_meal_plan,
        })

    return {"items": rows}
