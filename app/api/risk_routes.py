from fastapi import APIRouter, HTTPException
from app.models.schemas import PredictRequest, PredictResponse
from app.services.risk_predictor import predictor

router = APIRouter(prefix="/api/risk", tags=["Risk Prediction"])


@router.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    # Optional: enforce required columns exist
    missing = [c for c in predictor.feature_columns if c not in req.features]
    if missing:
        raise HTTPException(status_code=400, detail={"missing_features": missing})

    return predictor.predict(req.resident_id, req.features)
