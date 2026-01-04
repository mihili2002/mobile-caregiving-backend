from datetime import date, datetime
from uuid import uuid4

from typing import List, Optional, Literal
from pydantic import BaseModel, Field

from .day_meal_plan import DayMealPlan


MealPlanStatus = Literal["draft", "pending", "approved", "rejected", "completed"]


class MealPlan(BaseModel):
    id: str = Field(default_factory=lambda: f"Meal_plan_{str(uuid4())[:8]}")

    elder_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Link to the health submission used to generate this
    health_submission_id: Optional[str] = None

    # Week range
    start_date: date
    end_date: date

    status: MealPlanStatus = Field(default="draft")

    # Doctor approval workflow
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejected_by: Optional[str] = None
    rejected_at: Optional[datetime] = None
    doctor_feedback: Optional[str] = None

    days: List[DayMealPlan] = Field(default_factory=list)
