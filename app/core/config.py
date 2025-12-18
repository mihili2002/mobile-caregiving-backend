"""Application configuration.

Reads environment variables for service configuration.
"""
from pydantic import BaseSettings


class Settings(BaseSettings):
    project_name: str = "mobile-caregiving-backend"
    firebase_credentials: str | None = None  # Path to service account JSON
    firestore_emulator_host: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()
