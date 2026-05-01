"""Business logic / service layer for patient operations.

This module should interact with Firestore via helper utilities and
provide high-level methods consumed by API routes.
"""
from typing import List
from app.models.patient import Patient


class PatientService:
    def __init__(self):
        # Initialize Firestore client here (not implemented)
        pass

    def list_patients(self) -> List[Patient]:
        # Placeholder: query Firestore and return Patient instances
        return []
