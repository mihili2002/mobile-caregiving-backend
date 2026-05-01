from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone, timedelta
from firebase_admin import firestore

from app.models.schemas import PredictRequest, PredictResponse
from app.services.risk_predictor import predictor
from app.core.firebase import get_db

router = APIRouter(prefix="/api/risk", tags=["Risk Prediction"])


# --------------------------------------------
# Predict Risk
# --------------------------------------------
@router.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):

    missing = [c for c in predictor.feature_columns if c not in req.features]
    if missing:
        raise HTTPException(status_code=400, detail={"missing_features": missing})

    result = predictor.predict(req.resident_id, req.features)

    # Save to Firestore
    try:
        db = get_db()

        preds = result["predictions"]

        doc = {
            "residentId": req.resident_id,
            "predictions": preds,
            "depProb": preds["Depression_Risk"]["probability"],
            "anxProb": preds["Anxiety_Risk"]["probability"],
            "insProb": preds["Insomnia_Risk"]["probability"],
            "emoProb": preds["Emotional_WellBeing_Risk"]["probability"],
            "depLevel": preds["Depression_Risk"]["level"],
            "anxLevel": preds["Anxiety_Risk"]["level"],
            "insLevel": preds["Insomnia_Risk"]["level"],
            "emoLevel": preds["Emotional_WellBeing_Risk"]["level"],
            "createdAt": firestore.SERVER_TIMESTAMP,
            "createdAtClient": datetime.now(timezone.utc).isoformat(),
        }

        db.collection("risk_assessments").add(doc)

    except Exception as e:
        print("Firestore save error:", str(e))

    return result


# --------------------------------------------
# Get Risk History (FIXED)
# --------------------------------------------
@router.get("/history")
def get_history(
    resident_id: str = Query(...),
    days: int = Query(30, ge=1, le=365),
):
    try:
        db = get_db()

        since = datetime.now(timezone.utc) - timedelta(days=days)

        # 🔥 Optimized query (limit prevents quota abuse)
        q = (
            db.collection("risk_assessments")
            .where("residentId", "==", resident_id)
            .order_by("createdAt", direction=firestore.Query.ASCENDING)
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

            data.append(
                {
                    "id": d.id,
                    "residentId": row.get("residentId"),
                    "createdAt": created_iso,
                    "depProb": row.get("depProb"),
                    "anxProb": row.get("anxProb"),
                    "insProb": row.get("insProb"),
                    "emoProb": row.get("emoProb"),
                }
            )

        return {
            "resident_id": resident_id,
            "count": len(data),
            "items": data,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))