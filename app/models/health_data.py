from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Dict, Any
from datetime import datetime
from uuid import uuid4

SubmissionStatus = Literal["pending", "approved", "rejected"]

class ElderHealthSubmissionIn(BaseModel):
    # ----- Basic Information -----
    age: int = Field(..., ge=0)
    gender: Literal["Male", "Female"]

    height_cm: float = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)
    bmi: Optional[float] = None

    # ----- Health Conditions -----
    chronic_conditions: List[
        Literal["Diabetes", "Hypertension", "Heart Disease"]
    ] = Field(default_factory=list)

    genetic_risk: bool = False

    blood_pressure: Dict[str, Optional[int]] = Field(
        default_factory=lambda: {"systolic": None, "diastolic": None}
    )

    blood_sugar_mg_dl: Optional[float] = None
    cholesterol_mg_dl: Optional[float] = None

    # ----- Lifestyle -----
    daily_steps: Optional[int] = None
    exercise_frequency: Optional[int] = None
    sleep_hours: Optional[float] = None
    smoking: bool = False
    alcohol: bool = False

    # ----- Dietary Preferences -----
    dietary_habit: Literal["Vegetarian", "Vegan", "Non-Vegetarian"]
    food_allergies: Optional[str] = None
    preferred_cuisine: Optional[
        Literal["Indian", "Chinese", "Mediterranean", "Continental", "Mixed"]
    ] = None
    food_aversions: Optional[str] = None
    caloric_intake: Optional[float] = None
    protein_intake: Optional[float] = None
    carbohydrate_intake: Optional[float] = None
    fat_intake: Optional[float] = None

    # Extensibility
    extra: Optional[Dict[str, Any]] = None



class ElderHealthSubmission(ElderHealthSubmissionIn):
    id: str = Field(default_factory=lambda: str(uuid4()))
    elder_id: str = Field(..., description="UID of the elder patient")

    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    status: SubmissionStatus = Field(default="pending")

    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    doctor_notes: Optional[str] = None
