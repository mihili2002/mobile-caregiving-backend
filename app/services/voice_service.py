import os
import requests
from typing import Optional
from app.services.logger import log_debug

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"

# Mapping Task Categories to OpenAI Voices
# | Task Category         | Voice Style        | Tone            | OpenAI Voice |
# | ---------------------- | ------------------ | --------------- | ------------ |
# | 🩺 Health & Medication | Calm Nurse Voice   | Gentle, serious | shimmer      |
# | 🍽 Meals               | Warm Caregiver     | Friendly        | nova         |
# | 👨👩👧 Social        | Cheerful Companion | Happy           | alloy        |
# | 📖 Leisure             | Soft Relaxed Voice | Calm            | echo         |
# | ⚠️ Urgent Alerts       | Clear Firm Voice   | Direct          | onyx         |

VOICE_MAP = {
    "health": "shimmer",
    "medication": "shimmer",
    "meals": "nova",
    "social": "alloy",
    "leisure": "echo",
    "urgent": "onyx",
    "common": "nova", # Default to Warm Caregiver
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

    def generate_voice_reminder(self, text: str, category: str, output_path: str) -> bool:
        """
        Generates an audio file from text using OpenAI TTS.
        """
        if not self.api_key:
            log_debug("tts_error", {"error": "OpenAI API Key missing"})
            return False

        voice = VOICE_MAP.get(category.lower(), "nova")
        
        # Speed Mapping: 
        # Health: Slightly slower (0.85)
        # Meals/Social: Normal (1.0)
        # Leisure: Slower (0.8)
        # Urgent: Slightly faster (1.1)
        speed = 1.0
        if category in ["health", "medication"]: speed = 0.85
        elif category == "leisure": speed = 0.8
        elif category == "urgent": speed = 1.1

        payload = {
            "model": "tts-1",
            "input": text,
            "voice": voice,
            "speed": speed
        }

        try:
            response = requests.post(self.url, headers=self._headers(), json=payload, timeout=30)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            return True
        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg:
                log_debug("tts_forbidden", {"error": error_msg, "text": text, "model": "tts-1"})
            else:
                log_debug("tts_api_error", {"error": error_msg, "text": text})
            return False

voice_service = VoiceService()
