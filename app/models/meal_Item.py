from pydantic import BaseModel
from typing import List, Optional, Literal

MealType = Literal["breakfast", "lunch", "dinner", "snacks"]

class MealItem(BaseModel):
    name: str
    notes: Optional[str] = None