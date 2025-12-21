"""Pydantic model for health sensor data and records."""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class HealthData(BaseModel):
    # Metadata
    id: Optional[str] = None
    patient_id: str = Field(..., description="UID of the patient")
    timestamp: Optional[str] = None
    notes: Optional[str] = None
    

    # Demographics
    age: Optional[int] = Field(None, ge=0)
    gender: Optional[str] = None

    # Body metrics
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    bmi: Optional[float] = None

    # Medical info
    chronic_disease: Optional[str] = None
    genetic_risk_factor: Optional[bool] = None
    allergies: Optional[str] = None

    # Vitals
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    cholesterol_level: Optional[int] = None
    blood_sugar_level: Optional[int] = None

    # Lifestyle
    daily_steps: Optional[int] = None
    exercise_frequency: Optional[int] = Field(
        None, description="Exercise sessions per week"
    )
    sleep_hours: Optional[float] = None
    alcohol_consumption: Optional[bool] = None
    smoking_habit: Optional[bool] = None

    # Nutrition
    dietary_habits: Optional[str] = None
    caloric_intake: Optional[int] = None
    protein_intake: Optional[int] = None
    carbohydrate_intake: Optional[int] = None
    fat_intake: Optional[int] = None
    preferred_cuisine: Optional[str] = None
    food_aversions: Optional[str] = None

    # Raw sensor / extensibility
    vitals: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional raw or device-reported vitals (extensible)",
    )
