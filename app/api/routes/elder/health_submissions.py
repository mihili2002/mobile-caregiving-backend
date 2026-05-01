from uuid import uuid4

from fastapi import APIRouter, Depends, Body, HTTPException, Query
from datetime import datetime, timezone
from typing import Dict, Any, List

from app.api.deps import require_role, get_current_user
from app.core.firebase import get_db
from app.models.health_data import ElderHealthSubmission, ElderHealthSubmissionIn

router = APIRouter(prefix="/elder/health-submissions", tags=["elder_health_submissions"])


@router.post("/", status_code=201)
async def upsert_submission(
    payload: ElderHealthSubmissionIn = Body(...),
    user=Depends(require_role(["caregiver", "doctor"])),
):
    db = get_db()
    # exclude_unset=True ensures that fields the current user didn't fill 
    # (like Dietary vs Medical) aren't overwritten with null.
    incoming_data = payload.dict(exclude_unset=True) 
    
    target_elder_id = incoming_data.get("elder_id")

    # Look for a pending submission for this specific elder
    existing_docs = db.collection("elder_health_submissions") \
        .where("elder_id", "==", target_elder_id) \
        .where("status", "==", "pending") \
        .order_by("submitted_at", direction="DESCENDING") \
        .limit(1).get()

    if existing_docs:
        # --- UPDATE MODE ---
        doc_ref = existing_docs[0].reference
        # Merge incoming data into existing document
        doc_ref.update(incoming_data)
        return {"id": doc_ref.id, "status": "updated"}
    else:
        # --- CREATE MODE ---
        new_id = str(uuid4())
        full_data = {
            **incoming_data,
            "id": new_id,
            "status": "pending",
            "submitted_at": datetime.now(timezone.utc),
        }
        db.collection("elder_health_submissions").document(new_id).set(full_data)
        return {"id": new_id, "status": "created"}


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


@router.get("/")
async def get_elder_submissions(
    elder_id: str = Query(...),
    user=Depends(get_current_user),
):
    """
    Get all submissions for a specific elder.

    Returns a list of submissions directly (matches frontend expected format).
    User can access their own submissions or has permission as doctor/admin.
    """
    db = get_db()

    # Authorization: user can access their own submissions or if they're doctor/admin
    if user["uid"] != elder_id:
        # For now, allow doctors and admins to view any elder's submissions
        from app.api.deps import get_user_role
        try:
            role = get_user_role(user["uid"])
            if role not in ["doctor", "admin", "therapist"]:
                raise HTTPException(status_code=403, detail="Not authorized")
        except HTTPException:
            raise HTTPException(status_code=403, detail="Not authorized")

    docs = (
        db.collection("elder_health_submissions")
        .where("elder_id", "==", elder_id)
        .order_by("submitted_at", direction="DESCENDING")
        .stream()
    )

    items = [{"id": d.id, **(d.to_dict() or {})} for d in docs]
    return items


@router.get("/list/my", response_model=Dict[str, Any])
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
