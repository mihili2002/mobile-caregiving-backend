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

Timing = Literal["before_meal", "after_meal", "with_meal", "unknown"]
Meal = Literal["breakfast", "lunch", "dinner"]

class Medication(BaseModel):
    drug_name: str = Field(..., min_length=1)
    dosage: str = Field(..., min_length=1)          # "500 mg", "1 tab", etc.
    frequency: Optional[Union[str, List[str]]] = None
    timing: Optional[str] = "unknown"
    meals: Optional[List[Meal]] = None              # which meals
    duration: Optional[str] = None                  # "7 days", "1 month"
    notes: Optional[str] = None

    @field_validator('timing', mode='before')
    @classmethod
    def validate_timing(cls, v):
        allowed = {"before_meal", "after_meal", "with_meal", "unknown"}
        if v not in allowed:
            return "unknown"
        return v

    @field_validator('meals', mode='before')
    @classmethod
    def validate_meals(cls, v):
        if v is None:
            return None
        valid_meals = {"breakfast", "lunch", "dinner"}
        # Filter valid items only, ensuring lowercase
        if isinstance(v, list):
            return [m.lower() for m in v if isinstance(m, str) and m.lower() in valid_meals]
        return None

class ExtractionResponse(BaseModel):
    elder_id: str
    medications: List[Medication]
    used_method: str  # "vision_llm" or "ocr_fallback"
