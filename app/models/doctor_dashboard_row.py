from pydantic import BaseModel
from typing import Optional

from .health_data import ElderHealthSubmission
from .meal_plan import MealPlan


class DoctorDashboardRow(BaseModel):
    elder_id: str
    elder_name: Optional[str] = None

    latest_submission: Optional[ElderHealthSubmission] = None
    latest_meal_plan: Optional[MealPlan] = None