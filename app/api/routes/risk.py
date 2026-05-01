from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone, timedelta
from firebase_admin import firestore

from app.models.schemas import PredictRequest, PredictResponse
from app.services.risk_predictor import predictor
from app.core.firebase import get_db

router = APIRouter(prefix="/risk", tags=["Risk Prediction"])


# ====================================================
# AI Risk Prediction
# ====================================================

@router.post("/predict")
def predict(req: PredictRequest):

    # 1) Validate required ML features
    missing = [c for c in predictor.feature_columns if c not in req.features]

    if missing:
        raise HTTPException(status_code=400, detail={"missing_features": missing})

    # 2) Run ML prediction
    result = predictor.predict(req.resident_id, req.features)
    preds = result["predictions"]

    # 3) Build Firestore document
    doc = {
        "residentId": req.resident_id,
        "features": req.features,
        "predictions": preds,

        # flat numeric fields for charts
        "depProb": preds["Depression_Risk"]["probability"],
        "anxProb": preds["Anxiety_Risk"]["probability"],
        "insProb": preds["Insomnia_Risk"]["probability"],
        "emoProb": preds["Emotional_WellBeing_Risk"]["probability"],

        # risk levels
        "depLevel": preds["Depression_Risk"]["level"],
        "anxLevel": preds["Anxiety_Risk"]["level"],
        "insLevel": preds["Insomnia_Risk"]["level"],
        "emoLevel": preds["Emotional_WellBeing_Risk"]["level"],

        # clinical review fields
        "reviewStatus": "Pending Review",
        "reviewedBy": None,
        "reviewedAt": None,

        "createdAt": firestore.SERVER_TIMESTAMP,
        "createdAtClient": datetime.now(timezone.utc).isoformat(),
    }

    # 4) Save to Firestore
    try:
        db = get_db()

        doc_ref = db.collection("risk_assessments").document()

        doc_ref.set(doc)

        # IMPORTANT: capture the document ID
        risk_id = doc_ref.id

        print(f"Firestore saved: risk_assessments/{risk_id}")

    except Exception as e:
        print("Firestore save failed:", str(e))
        raise HTTPException(status_code=500, detail="Failed to save risk assessment")

    # return prediction result + risk_id
    result["risk_id"] = risk_id

    return result


# ====================================================
# Get Risk History (for charts)
# ====================================================

@router.get("/history")
def get_history(
    resident_id: str = Query(..., description="Resident ID"),
    days: int = Query(30, ge=1, le=365, description="How many past days to fetch"),
):

    db = get_db()

    since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        from google.cloud.firestore import FieldFilter
        q = (
            db.collection("risk_assessments")
            .where(filter=FieldFilter("residentId", "==", resident_id))
            .where(filter=FieldFilter("createdAt", ">=", since))
            .order_by("createdAt", direction=firestore.Query.ASCENDING)
        )

        docs = q.stream()

        data = []

        for d in docs:

            row = d.to_dict()

            created_at = row.get("createdAt")

            created_iso = None

            if created_at is not None:
                try:
                    created_iso = created_at.datetime.replace(
                        tzinfo=timezone.utc
                    ).isoformat()
                except Exception:
                    created_iso = str(created_at)

            data.append(
                {
                    "id": d.id,
                    "residentId": row.get("residentId"),
                    "createdAt": created_iso,
                    "depProb": row.get("depProb"),
                    "anxProb": row.get("anxProb"),
                    "insProb": row.get("insProb"),
                    "emoProb": row.get("emoProb"),
                    "reviewStatus": row.get("reviewStatus", "Pending Review"),
                }
            )

        return {
            "resident_id": resident_id,
            "days": days,
            "count": len(data),
            "items": data,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})


# ====================================================
# Approve Risk Result (Mental Health Professional)
# ====================================================

@router.post("/approve_risk_result")
def approve_risk_result(payload: dict):

    db = get_db()

    risk_id = payload.get("risk_id")
    approved_by = payload.get("approved_by", "Mental Health Professional")

    if not risk_id:
        raise HTTPException(status_code=400, detail="risk_id required")

    try:

        db.collection("risk_assessments").document(risk_id).update({
            "reviewStatus": "Approved",
            "reviewedBy": approved_by,
            "reviewedAt": datetime.utcnow().isoformat()
        })

        return {"message": "Risk result approved"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ====================================================
# Reject Risk Result
# ====================================================

@router.post("/reject_risk_result")
def reject_risk_result(payload: dict):

    db = get_db()

    risk_id = payload.get("risk_id")

    if not risk_id:
        raise HTTPException(status_code=400, detail="risk_id required")

    try:

        db.collection("risk_assessments").document(risk_id).update({
            "reviewStatus": "Rejected"
        })

        return {"message": "Risk result rejected"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))