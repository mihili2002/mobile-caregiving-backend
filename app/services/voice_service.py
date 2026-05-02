import os
import requests
from typing import Optional
from app.services.logger import log_debug

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"

VOICE_PROFILES = {
    "health": {"voice": "shimmer", "speed": 0.6},
    "medication": {"voice": "shimmer", "speed": 0.5},
    "meal": {"voice": "echo", "speed": 0.7},
    "meals": {"voice": "echo", "speed": 0.6},
    "social": {"voice": "nova", "speed": 0.9},
    "leisure": {"voice": "echo", "speed": 0.6},
    "therapy": {"voice": "echo", "speed": 0.7},
    "urgent": {"voice": "onyx", "speed": 1.0},
    "common": {"voice": "alloy", "speed": 0.9},
}

class VoiceService:
    def __init__(self):
        self.api_key = OPENAI_API_KEY
        self.url = OPENAI_TTS_URL

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate_voice_reminder(
        self,
        text: str,
        category: str = "common",
        forgotten: bool = False,
    ) -> Optional[bytes]:
        if not self.api_key:
            log_debug("tts_error", {"error": "OpenAI API Key missing"})
            return None

        cat = category.lower() if category else "common"

        # Forgotten reminders should sound firm/urgent.
        if forgotten:
            cat = "urgent"

        profile = VOICE_PROFILES.get(cat, VOICE_PROFILES["common"])

        payload = {
            "model": "tts-1",
            "input": text,
            "voice": profile["voice"],
            "speed": profile["speed"],
            "response_format": "mp3",
        }

        try:
            response = requests.post(
                self.url,
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return response.content

        except Exception as e:
            error_msg = str(e)
            log_debug(
                "tts_api_error",
                {
                    "error": error_msg,
                    "text": text,
                    "category": cat,
                    "forgotten": forgotten,
                },
            )
            return None

voice_service = VoiceService()