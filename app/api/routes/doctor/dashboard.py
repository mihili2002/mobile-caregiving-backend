from fastapi import APIRouter, Depends
from typing import Dict, Any, List, Optional

from app.api.deps import require_role
from app.core import firebase

router = APIRouter(prefix="/doctor/dashboard", tags=["doctor_dashboard"])


@router.get("/")
async def doctor_dashboard(user=Depends(require_role(["doctor"]))):
    # get latest submission per elder (simple version)
    submissions = firebase.db.collection("elder_health_submissions").stream()

    # group by elder_id
    latest_map: Dict[str, Dict[str, Any]] = {}

    for doc in submissions:
        data = doc.to_dict()
        elder_id = data.get("elder_id")
        if not elder_id:
            continue

        # keep the most recent submission
        prev = latest_map.get(elder_id)
        if prev is None or data.get("submitted_at") > prev.get("submitted_at"):
            latest_map[elder_id] = {"id": doc.id, **data}

    rows: List[Dict[str, Any]] = []

    for elder_id, latest_submission in latest_map.items():
        # Find latest meal plan for this elder (optional)
        meal_docs = (
            firebase.db.collection("meal_plans")
            .where("elder_id", "==", elder_id)
            .order_by("created_at", direction="DESCENDING")
            .limit(1)
            .stream()
        )
        meal_items = [{"id": d.id, **d.to_dict()} for d in meal_docs]
        latest_meal_plan = meal_items[0] if meal_items else None

        rows.append({
            "elder_id": elder_id,
            "elder_name": None,  # you can later enrich from users collection
            "latest_submission": latest_submission,
            "latest_meal_plan": latest_meal_plan,
        })

    return {"items": rows}
