from typing import Any, Dict
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

class PredictRequest(BaseModel):
    resident_id: str = Field(..., examples=["resident_001"])
    features: Dict[str, Any]


class RiskItem(BaseModel):
    probability: float
    level: str


class PredictResponse(BaseModel):
    resident_id: str
    predictions: Dict[str, RiskItem]
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any, Literal, Union

# Define data models to ensure type safety and clearer APIs

class UserProfile(BaseModel):
    uid: str
    age: Optional[int] = 65
    gender: Optional[str] = 'Male'
    mobility_level: Optional[str] = 'Walking'
    cognitive_level: Optional[str] = 'Normal'
    mental_health_issues: Optional[List[str]] = []

class TaskInput(BaseModel):
    uid: str
    task_name: str
    time_string: Optional[str] = '12:00'
    type: Optional[str] = 'common'
    # Flexible for additional fields
    extra_data: Optional[dict] = {}

from enum import Enum

class Timing(str, Enum):
    before_meal = "before_meal"
    after_meal = "after_meal"
    with_meal = "with_meal"
    bedtime = "bedtime"
    morning = "morning"
    afternoon = "afternoon"
    evening = "evening"
    as_needed = "as_needed"
    unknown = "unknown"

Meal = Literal["breakfast", "lunch", "dinner"]

class Medication(BaseModel):
    drug_name: str = Field(..., min_length=1)
    strength: Optional[str] = None                  # "50 mg"
    dosage: Optional[str] = None                    # legacy field
    dose_pattern: Optional[str] = None              # "1-0-1", "1 tab"
    dose_unit: Optional[str] = None                 # "tab", "ml"
    dose_form: Optional[str] = None                 # "tablet", "capsule", "syrup"
    frequency_per_day: Optional[int] = None         # 1, 2, 3
    frequency_text: Optional[str] = None            # "BD", "OD"
    is_prn: bool = False                            # "as needed"
    timing: Timing = Timing.unknown
    meals: Optional[List[Meal]] = None              # which meals
    duration: Optional[str] = None                  # legacy field
    duration_days: Optional[int] = None
    duration_text: Optional[str] = None             # "2 weeks"
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    route: Optional[str] = None                     # "oral", "topical"
    notes: Optional[str] = None
    confidence: float = 0.0
    raw_text: Optional[str] = None                  # specific snippet for this med

    @field_validator('timing', mode='before')
    @classmethod
    def validate_timing(cls, v):
        if isinstance(v, Timing):
            return v
        try:
            return Timing(v)
        except (ValueError, KeyError):
            return Timing.unknown

    @field_validator('meals', mode='before')
    @classmethod
    def validate_meals(cls, v):
        if v is None:
            return None
        valid_meals = {"breakfast", "lunch", "dinner"}
        if isinstance(v, list):
            return [m.lower() for m in v if isinstance(m, str) and m.lower() in valid_meals]
        return None

class ExtractionResponse(BaseModel):
    elder_id: str
    medications: List[Medication]
    used_method: str  # "vision_llm", "ocr_fallback", or "digital_pdf"
    raw_text: Optional[str] = None # Entire document text
