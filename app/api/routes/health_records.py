# app/api/routes/health_records.py
print("🔥 LOADED UPDATED health_records.py")

"""
Health records routes.

Patients submit health data which is stored in Firestore.
ML generates a suggested nutrition + meal plan.
Doctor approval is required before the plan is visible to patients.
"""

from fastapi import APIRouter, Depends, Body, HTTPException
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.api.deps import get_current_user, require_role
from app.core import firebase
from app.models.health_data import HealthData
from app.services.meal_plan_pipeline import build_meal_plan

router = APIRouter(prefix="/health_records", tags=["health_records"])


def _bool_to_yesno(v: Optional[bool]) -> str:
    if v is True:
        return "Yes"
    if v is False:
        return "No"
    return "nan"


def _first(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


@router.post("/", status_code=201)
async def submit_record(payload: HealthData = Body(...), user=Depends(get_current_user)):
    if user["uid"] != payload.patient_id and user.get("role") != "doctor":
        raise HTTPException(status_code=403, detail="Unauthorized submission")

    data: Dict[str, Any] = payload.dict(exclude_none=True)

    vitals: Dict[str, Any] = data.get("vitals") or {}

    # Prefer root fields, fallback to vitals
    height_cm = _first(data.get("height_cm"), vitals.get("height_cm"))
    weight_kg = _first(data.get("weight_kg"), vitals.get("weight_kg"))
    bmi = _first(data.get("bmi"), vitals.get("bmi"))

    # Compute BMI if missing and we have height+weight
    if bmi is None and height_cm and weight_kg:
        try:
            bmi = float(weight_kg) / ((float(height_cm) / 100) ** 2)
            bmi = round(bmi, 2)
        except Exception:
            bmi = None

    # Build ML features (MATCHES training column names)
    try:
        ml_features = {
            "Age": data.get("age"),
            "Gender": data.get("gender"),
            "Height_cm": height_cm,
            "Weight_kg": weight_kg,
            "BMI": bmi,
            "Chronic_Disease": data.get("chronic_disease"),

            "Blood_Pressure_Systolic": _first(data.get("blood_pressure_systolic"), vitals.get("blood_pressure_systolic")),
            "Blood_Pressure_Diastolic": _first(data.get("blood_pressure_diastolic"), vitals.get("blood_pressure_diastolic")),
            "Cholesterol_Level": _first(data.get("cholesterol_level"), vitals.get("cholesterol_level")),
            "Blood_Sugar_Level": _first(data.get("blood_sugar_level"), vitals.get("blood_sugar_level")),

            # These are bools in API model → strings for ML encoders
            "Genetic_Risk_Factor": _bool_to_yesno(data.get("genetic_risk_factor")),
            "Alcohol_Consumption": _bool_to_yesno(data.get("alcohol_consumption")),
            "Smoking_Habit": _bool_to_yesno(data.get("smoking_habit")),

            "Allergies": data.get("allergies"),
            "Daily_Steps": data.get("daily_steps"),
            "Exercise_Frequency": data.get("exercise_frequency"),
            "Sleep_Hours": data.get("sleep_hours"),
            "Dietary_Habits": data.get("dietary_habits"),
            "Caloric_Intake": data.get("caloric_intake"),
            "Protein_Intake": data.get("protein_intake"),
            "Carbohydrate_Intake": data.get("carbohydrate_intake"),
            "Fat_Intake": data.get("fat_intake"),
            "Preferred_Cuisine": data.get("preferred_cuisine"),
            "Food_Aversions": data.get("food_aversions"),
        }

        suggested_plan = build_meal_plan(ml_features)

    except Exception as e:
        suggested_plan = {"error": "Meal plan generation failed", "details": str(e)}

    record = {
        **data,
        "created_by": user["uid"],
        "suggested_meal_plan": suggested_plan,
        "nutrition_approved": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    doc_ref = firebase.db.collection("health_records").add(record)
    return {"id": doc_ref[1].id, "suggested_meal_plan": suggested_plan}


@router.get("/")
async def list_records(user=Depends(get_current_user)):
    coll = firebase.db.collection("health_records")

    role = user.get("role") or user.get("roles")
    if role == "doctor" or (isinstance(role, list) and "doctor" in role):
        docs = coll.stream()
    else:
        docs = coll.where("patient_id", "==", user["uid"]).stream()

    return {"items": [{"id": d.id, **d.to_dict()} for d in docs]}


@router.post("/{record_id}/approve")
async def approve_suggestion(record_id: str, user=Depends(require_role(["doctor"]))):
    ref = firebase.db.collection("health_records").document(record_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Record not found")
    ref.update({"nutrition_approved": True})
    return {"message": "Meal plan approved"}
