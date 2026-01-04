from fastapi import APIRouter, Depends, Body, HTTPException
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.api.deps import get_current_user, require_role
from app.core import firebase
from app.models.health_data import ElderHealthSubmission, ElderHealthSubmissionIn

router = APIRouter(prefix="/elder/health-submissions", tags=["elder_health_submissions"])


@router.post("/", status_code=201)
async def create_submission(
    payload: ElderHealthSubmissionIn = Body(...),
    user=Depends(require_role(["elder"])),
):
    data = payload.dict()
    # Calculate BMI if not provided
    if not data.get("bmi"):
        try:
            height_m = data.get("height_cm") / 100.0
            data["bmi"] = round(data.get("weight_kg") / (height_m * height_m), 2)
        except Exception:
            data["bmi"] = None

    submission = ElderHealthSubmission(
        **data,
        elder_id=user["uid"],
        status="pending",
        submitted_at=datetime.now(timezone.utc),
    )

    firebase.db.collection("elder_health_submissions") \
        .document(submission.id) \
        .set(submission.dict())

    return {"id": submission.id, "status": submission.status}



@router.get("/", response_model=Dict[str, Any])
async def list_my_submissions(user=Depends(require_role(["elder"]))):
    docs = (
        firebase.db.collection("elder_health_submissions")
        .where("elder_id", "==", user["uid"])
        .order_by("submitted_at", direction="DESCENDING")
        .stream()
    )
    items = [{"id": d.id, **d.to_dict()} for d in docs]
    return {"items": items}


@router.get("/latest", response_model=Dict[str, Any])
async def get_latest_submission(user=Depends(require_role(["elder"]))):
    docs = (
        firebase.db.collection("elder_health_submissions")
        .where("elder_id", "==", user["uid"])
        .order_by("submitted_at", direction="DESCENDING")
        .limit(1)
        .stream()
    )
    items = [{"id": d.id, **d.to_dict()} for d in docs]
    return {"item": items[0] if items else None}