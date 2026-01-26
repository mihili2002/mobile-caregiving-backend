from pydantic_settings import BaseSettings , SettingsConfigDict
from pathlib import Path
# from pydantic import BaseSettings

BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    project_name: str = "mobile-caregiving-backend"

    firebase_credentials: str | None = None
    firestore_emulator_host: str | None = None

    EMOTION_MODEL_DIR: str = str(BASE_DIR / "ml" / "member2_chatbot" / "models" / "emotion_model")

    # ✅ Add these:
    DIALOGFLOW_PROJECT_ID: str = "elderly-voice-bot-xvja"
    DIALOGFLOW_LANGUAGE_CODE: str = "en"

    

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
"""Application configuration.

Reads environment variables for service configuration.
"""






