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

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Fetch all records for this resident to avoid complex index requirements for now
        # and to handle older records that might be missing certain fields.
        q = db.collection("risk_assessments").where("residentId", "==", resident_id)
        docs = list(q.stream())

        items = []
        for d in docs:
            row = d.to_dict()
            
            # Use createdAt (Timestamp) or fallback to createdAtClient (ISO string)
            raw_ts = row.get("createdAt")
            created_dt = None
            
            if raw_ts:
                try:
                    if hasattr(raw_ts, "datetime"):
                        created_dt = raw_ts.datetime.replace(tzinfo=timezone.utc)
                    else:
                        created_dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                except:
                    pass
            
            if not created_dt and row.get("createdAtClient"):
                try:
                    created_dt = datetime.fromisoformat(row["createdAtClient"].replace("Z", "+00:00"))
                except:
                    pass
            
            # If still no date, use a very old date or skip
            if not created_dt:
                continue

            # Filter by days
            if created_dt < cutoff:
                continue

            items.append({
                "id": d.id,
                "residentId": row.get("residentId"),
                "createdAt": created_dt.isoformat(),
                "features": row.get("features", {}),
                "predictions": row.get("predictions", {}),
                "depProb": row.get("depProb"),
                "anxProb": row.get("anxProb"),
                "insProb": row.get("insProb"),
                "emoProb": row.get("emoProb"),
                "reviewStatus": row.get("reviewStatus", "Pending Review"),
                "_dt": created_dt # temp for sorting
            })

        # Sort by date descending (newest first) for the API response
        items.sort(key=lambda x: x["_dt"], reverse=True)
        
        # Clean up temp field
        for it in items:
            it.pop("_dt")

        return {
            "resident_id": resident_id,
            "count": len(items),
            "items": items,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))