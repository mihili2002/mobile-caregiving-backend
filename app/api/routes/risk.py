from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone, timedelta
from firebase_admin import firestore

from app.models.schemas import PredictRequest, PredictResponse
from app.services.risk_predictor import predictor
from app.core.firebase import get_db

router = APIRouter(prefix="/risk", tags=["Risk Prediction"])


@router.post("/predict", response_model=PredictResponse)
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

        # optional levels
        "depLevel": preds["Depression_Risk"]["level"],
        "anxLevel": preds["Anxiety_Risk"]["level"],
        "insLevel": preds["Insomnia_Risk"]["level"],
        "emoLevel": preds["Emotional_WellBeing_Risk"]["level"],

        "createdAt": firestore.SERVER_TIMESTAMP,
        "createdAtClient": datetime.now(timezone.utc).isoformat(),
    }

    # 4) Save to Firestore
    try:
        db = get_db()
        doc_ref = db.collection("risk_assessments").document()
        doc_ref.set(doc)
        print(f"✅ Firestore saved: risk_assessments/{doc_ref.id}")
    except Exception as e:
        print("⚠️ Firestore save failed:", str(e))

    return result


@router.get("/history")
def get_history(
    resident_id: str = Query(..., description="Resident ID"),
    days: int = Query(30, ge=1, le=365, description="How many past days to fetch"),
):
    """
    Returns risk_assessments in the last X days for this resident.
    Used for therapist graphs.
    """
    db = get_db()

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Firestore requires indexed query for where + order_by
    # createdAt is server timestamp, so we filter by createdAt >= since
    try:
        q = (
            db.collection("risk_assessments")
            .where("residentId", "==", resident_id)
            .where("createdAt", ">=", since)
            .order_by("createdAt", direction=firestore.Query.ASCENDING)
        )

        docs = q.stream()

        data = []
        for d in docs:
            row = d.to_dict()

            created_at = row.get("createdAt")
            # createdAt is a Firestore Timestamp, convert safely
            created_iso = None
            if created_at is not None:
                try:
                    created_iso = created_at.datetime.replace(tzinfo=timezone.utc).isoformat()
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
                }
            )

        return {"resident_id": resident_id, "days": days, "count": len(data), "items": data}

    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})
