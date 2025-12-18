"""Pydantic model for health sensor data and records."""
from pydantic import BaseModel
from typing import Optional, Dict, Any


class HealthData(BaseModel):
    id: Optional[str]
    patient_id: str
    timestamp: Optional[str]
    vitals: Optional[Dict[str, Any]]
    notes: Optional[str]
