"""Health-related business logic.

Contains helpers to store and query health records in Firestore.
"""
from app.models.health_data import HealthData


class HealthService:
    def __init__(self):
        pass

    def list_records(self, patient_id: str):
        return []
