from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone
from firebase_admin import firestore

from app.models.schemas import PredictRequest, PredictResponse
from app.services.risk_predictor import predictor
from app.core.firebase import get_db

router = APIRouter(prefix="/api/risk", tags=["Risk Prediction"])


# ====================================================
# Predict Risk
# ====================================================
@router.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):

    missing = [c for c in predictor.feature_columns if c not in req.features]

    if missing:
        raise HTTPException(status_code=400, detail={"missing_features": missing})

    result = predictor.predict(req.resident_id, req.features)
    preds = result["predictions"]

    try:
        db = get_db()

        doc = {
            "residentId": req.resident_id,

            # ✅ REQUIRED FOR UI
            "features": req.features,
            "predictions": preds,

            # chart values
            "depProb": preds["Depression_Risk"]["probability"],
            "anxProb": preds["Anxiety_Risk"]["probability"],
            "insProb": preds["Insomnia_Risk"]["probability"],
            "emoProb": preds["Emotional_WellBeing_Risk"]["probability"],

            # levels
            "depLevel": preds["Depression_Risk"]["level"],
            "anxLevel": preds["Anxiety_Risk"]["level"],
            "insLevel": preds["Insomnia_Risk"]["level"],
            "emoLevel": preds["Emotional_WellBeing_Risk"]["level"],

            # review
            "reviewStatus": "Pending Review",
            "reviewedBy": None,
            "reviewedAt": None,

            "createdAt": firestore.SERVER_TIMESTAMP,
            "createdAtClient": datetime.now(timezone.utc).isoformat(),
        }

        db.collection("risk_assessments").add(doc)

    except Exception as e:
        print("Firestore save error:", str(e))

    return result


# ====================================================
# Get Risk History (FINAL CLEAN VERSION)
# ====================================================
@router.get("/history")
def get_history(
    resident_id: str = Query(...),
    days: int = Query(30, ge=1, le=365),
):
    try:
        db = get_db()

        q = (
            db.collection("risk_assessments")
            .where("residentId", "==", resident_id)
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(50)
        )

        docs = q.stream()
        data = []

        for d in docs:
            row = d.to_dict()

            created_at = row.get("createdAt")
            created_iso = None

            if created_at:
                try:
                    created_iso = created_at.datetime.replace(
                        tzinfo=timezone.utc
                    ).isoformat()
                except:
                    created_iso = str(created_at)

            data.append({
                "id": d.id,
                "residentId": row.get("residentId"),
                "createdAt": created_iso,

                # 🔥 ALWAYS RETURN (even if empty)
                "features": row.get("features", {}),
                "predictions": row.get("predictions", {}),

                # chart
                "depProb": row.get("depProb"),
                "anxProb": row.get("anxProb"),
                "insProb": row.get("insProb"),
                "emoProb": row.get("emoProb"),

                "reviewStatus": row.get("reviewStatus", "Pending Review"),
            })

        return {
            "resident_id": resident_id,
            "count": len(data),
            "items": data,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ====================================================
# Approve
# ====================================================
@router.post("/approve_risk_result")
def approve_risk_result(payload: dict):

    db = get_db()

    risk_id = payload.get("risk_id")
    approved_by = payload.get("approved_by", "Therapist")

    if not risk_id:
        raise HTTPException(status_code=400, detail="risk_id required")

    db.collection("risk_assessments").document(risk_id).update({
        "reviewStatus": "Approved",
        "reviewedBy": approved_by,
        "reviewedAt": datetime.utcnow().isoformat()
    })

    return {"message": "Approved"}


# ====================================================
# Reject
# ====================================================
@router.post("/reject_risk_result")
def reject_risk_result(payload: dict):

    db = get_db()

    risk_id = payload.get("risk_id")

    if not risk_id:
        raise HTTPException(status_code=400, detail="risk_id required")

    db.collection("risk_assessments").document(risk_id).update({
        "reviewStatus": "Rejected"
    })

    return {"message": "Rejected"}