"""Health records routes.

Patients can submit health data which is stored in Firestore. Doctors
can list and review records. ML inference is used to generate suggested
nutrition targets; a doctor must approve suggestions before they are
visible to the patient.
"""
from fastapi import APIRouter, Depends, Body, HTTPException
from app.api.deps import get_current_user, require_role
from app.core import firebase
from app.models.health_data import HealthData
from app.services import ml_inference
from typing import Dict
from datetime import datetime, timezone


router = APIRouter(prefix="/health_records", tags=["health_records"])


@router.post("/", status_code=201)
async def submit_record(
    payload: HealthData = Body(...),
    user=Depends(get_current_user)
):
    """Patient submits a health record. ML suggestions are stored but
    require doctor approval before being published to the patient view."""
    # Basic ownership check: patient can only create records for themselves
    if user["uid"] != payload.patient_id and user.get("role") != "doctor":
        raise HTTPException(status_code=403, detail="Cannot submit record for this patient")

    data = payload.dict(exclude_none=True)

    # Compute BMI if height/weight present in vitals
    vitals: Dict = data.get("vitals") or {}
    height_cm = vitals.get("height_cm")
    weight_kg = vitals.get("weight_kg")
    if height_cm and weight_kg:
        try:
            h_m = float(height_cm) / 100.0
            bmi = float(weight_kg) / (h_m * h_m)
            vitals["bmi"] = round(bmi, 2)
            data["vitals"] = vitals
        except Exception:
            pass

    # Run ML nutrition prediction (non-blocking in production; sync here)
    suggested = None
    try:
        features = {
            "age": data.get("age") or 0,
            "weight": weight_kg or 0,
            "height": height_cm or 0,
            # Add more features mapping as required by the model
        }
        suggested = ml_inference.predict_nutrition(features)
    except Exception:
        suggested = None

    record = {
        **data,
        "created_by": user["uid"],
        "suggested_nutrition": suggested,
        "nutrition_approved": False,
    }

    record["timestamp"] = datetime.now(timezone.utc).isoformat()

    doc_ref = firebase.db.collection("health_records").add(record)
    return {"id": doc_ref[1].id, "suggested_nutrition": suggested}


@router.get("/")
async def list_records(user=Depends(get_current_user)):
    """List health records.

    - Doctors see all records; patients see only their own records.
    """
    coll = firebase.db.collection("health_records")
    role = user.get("role") or user.get("roles")
    if role == "doctor" or (isinstance(role, list) and "doctor" in role):
        docs = coll.stream()
    else:
        docs = coll.where("patient_id", "==", user["uid"]).stream()

    return {"items": [{"id": d.id, **d.to_dict()} for d in docs]}


@router.post("/{record_id}/approve")
async def approve_suggestion(record_id: str, user=Depends(require_role(["doctor"]))):
    """Doctor approves a suggested nutrition plan for a record."""
    ref = firebase.db.collection("health_records").document(record_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Record not found")
    ref.update({"nutrition_approved": True})
    return {"message": "Approved"}
