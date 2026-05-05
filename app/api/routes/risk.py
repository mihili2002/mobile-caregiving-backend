from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone, timedelta
from firebase_admin import firestore

from app.models.schemas import PredictRequest
from app.services.risk_predictor import predictor
from app.core.firebase import get_db

router = APIRouter(prefix="/risk", tags=["Risk Prediction"])


# ====================================================
# Predict Risk (FINAL FIX)
# ====================================================
@router.post("/predict")
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

            # 🔥 REQUIRED FOR FRONTEND
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
        raise HTTPException(status_code=500, detail="Failed to save")

    return result


# ====================================================
# Get History (LATEST ONLY)
# ====================================================
@router.get("/history")
def get_history(
    resident_id: str = Query(...),
    days: int = Query(30),
):
    try:
        db = get_db()

        q = (
            db.collection("risk_assessments")
            .where("residentId", "==", resident_id)
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(1)  # 🔥 ONLY LATEST
        )

        docs = list(q.stream())

        if not docs:
            return {
                "resident_id": resident_id,
                "count": 0,
                "items": [],
            }

        d = docs[0]
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

        # 🔥 RETURN CLEAN LATEST DATA
        item = {
            "id": d.id,
            "residentId": row.get("residentId"),
            "createdAt": created_iso,
            "features": row.get("features", {}),
            "predictions": row.get("predictions", {}),
            "depProb": row.get("depProb"),
            "anxProb": row.get("anxProb"),
            "insProb": row.get("insProb"),
            "emoProb": row.get("emoProb"),
            "reviewStatus": row.get("reviewStatus", "Pending Review"),
        }

        return {
            "resident_id": resident_id,
            "count": 1,
            "items": [item],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))