from typing import List, Literal
from pydantic import BaseModel, Field

from .meal_Item import MealItem


class DayMealPlan(BaseModel):
    day: Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    breakfast: List[MealItem] = Field(default_factory=list)
    lunch: List[MealItem] = Field(default_factory=list)
    dinner: List[MealItem] = Field(default_factory=list)
    snacks: List[MealItem] = Field(default_factory=list)
