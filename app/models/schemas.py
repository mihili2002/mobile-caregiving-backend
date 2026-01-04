from typing import Any, Dict
from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    resident_id: str = Field(..., examples=["resident_001"])
    features: Dict[str, Any]


class RiskItem(BaseModel):
    probability: float
    level: str


class PredictResponse(BaseModel):
    resident_id: str
    predictions: Dict[str, RiskItem]
