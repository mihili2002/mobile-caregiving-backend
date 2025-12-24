# app/core/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Where your HuggingFace emotion model folder is (local path)
    EMOTION_MODEL_DIR: str = "models/emotion"

    # Dialogflow (optional)
    DIALOGFLOW_PROJECT_ID: str = ""
    DIALOGFLOW_LANGUAGE_CODE: str = "en"

    # If you want to read from a .env file, keep this:
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
