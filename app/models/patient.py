"""Pydantic model for patient metadata stored in Firestore.

This is NOT an ML model. Use this for request/response validation.
"""
from pydantic import BaseModel, EmailStr
from typing import Optional


class Patient(BaseModel):
    id: Optional[str]
    name: str
    email: Optional[EmailStr]
    age: Optional[int]
    notes: Optional[str]
