from fastapi import APIRouter, Depends, Body, HTTPException
from datetime import datetime, timezone
from typing import Dict, Any

from app.api.deps import require_role
from app.core.firebase import get_db
from app.models.health_data import ElderHealthSubmission, ElderHealthSubmissionIn

router = APIRouter(prefix="/elder/health-submissions", tags=["elder_health_submissions"])


@router.post("/", status_code=201)
async def create_submission(
    payload: ElderHealthSubmissionIn = Body(...),
    user=Depends(require_role(["elder"])),
):
    db = get_db()

    data = payload.dict()

    # Calculate BMI if not provided
    if not data.get("bmi"):
        try:
            height_cm = data.get("height_cm")
            weight_kg = data.get("weight_kg")
            if height_cm and weight_kg:
                height_m = height_cm / 100.0
                data["bmi"] = round(weight_kg / (height_m * height_m), 2)
            else:
                data["bmi"] = None
        except Exception:
            data["bmi"] = None

    submission = ElderHealthSubmission(
        **data,
        elder_id=user["uid"],
        status="pending",
        submitted_at=datetime.now(timezone.utc),
    )

    db.collection("elder_health_submissions") \
        .document(submission.id) \
        .set(submission.dict())

    return {"id": submission.id, "status": submission.status}


@router.put("/{submission_id}")
async def update_submission(
    submission_id: str,
    payload: ElderHealthSubmissionIn = Body(...),
    user=Depends(require_role(["elder"])),
):
    db = get_db()

    ref = db.collection("elder_health_submissions").document(submission_id)
    doc = ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Submission not found")

    existing = doc.to_dict() or {}

    # 🔒 Ownership check
    if existing.get("elder_id") != user["uid"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # 🔒 Only allow updates if still pending
    if existing.get("status") != "pending":
        raise HTTPException(
            status_code=400,
            detail="Approved or rejected submissions cannot be edited",
        )

    data = payload.dict()

    # Recalculate BMI if needed
    if not data.get("bmi"):
        try:
            height_cm = data.get("height_cm")
            weight_kg = data.get("weight_kg")
            if height_cm and weight_kg:
                height_m = height_cm / 100.0
                data["bmi"] = round(weight_kg / (height_m * height_m), 2)
            else:
                data["bmi"] = None
        except Exception:
            data["bmi"] = None

    # Preserve immutable fields
    data.update(
        {
            "elder_id": existing.get("elder_id"),
            "status": existing.get("status"),
            "submitted_at": datetime.now(timezone.utc),
        }
    )

    ref.update(data)

    return {"id": submission_id, "status": "updated"}


@router.get("/", response_model=Dict[str, Any])
async def list_my_submissions(user=Depends(require_role(["elder"]))):
    db = get_db()

    docs = (
        db.collection("elder_health_submissions")
        .where("elder_id", "==", user["uid"])
        .order_by("submitted_at", direction="DESCENDING")
        .stream()
    )
    items = [{"id": d.id, **(d.to_dict() or {})} for d in docs]
    return {"items": items}


@router.get("/latest", response_model=Dict[str, Any])
async def get_latest_submission(user=Depends(require_role(["elder"]))):
    db = get_db()

    docs = (
        db.collection("elder_health_submissions")
        .where("elder_id", "==", user["uid"])
        .order_by("submitted_at", direction="DESCENDING")
        .limit(1)
        .stream()
    )
    items = [{"id": d.id, **(d.to_dict() or {})} for d in docs]
    return {"item": items[0] if items else None}


@router.get("/{submission_id}")
async def get_submission_details(
    submission_id: str,
    user=Depends(require_role(["elder"])),
):
    db = get_db()

    doc = db.collection("elder_health_submissions") \
        .document(submission_id) \
        .get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Submission not found")

    data = doc.to_dict() or {}

    # 🔒 Ownership check (recommended, keeps this consistent with update)
    if data.get("elder_id") != user["uid"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    return {"id": doc.id, **data}
