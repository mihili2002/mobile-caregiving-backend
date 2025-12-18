"""Pydantic model for caregiver metadata."""
from pydantic import BaseModel, EmailStr
from typing import Optional


class Caregiver(BaseModel):
    id: Optional[str]
    name: str
    email: Optional[EmailStr]
    phone: Optional[str]
