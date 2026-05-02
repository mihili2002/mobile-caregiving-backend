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
# | 🍽 Meals               | Normal Male Voice  | Friendly        | echo         |
# | 👨👩👧 Social        | Cheerful Companion | Happy, bright   | nova         |
# | 📖 Leisure & Therapy   | Soft Relaxed Voice | Calm, slow      | echo         |
# | ⚠️ Urgent Alerts       | Clear Firm Voice   | Deep, fast      | onyx         |
# | ⚙️ Common             | Default Male Voice | Neutral         | alloy        |

VOICE_PROFILES = {
    "health": {
        "gender": "female",
        "style": "calm, caring",
        "voice": "shimmer",
        "speed": 0.5,
    },
    "medication": {
        "gender": "female",
        "style": "calm, caring",
        "voice": "shimmer",
        "speed": 0.5,
    },
    "meal": {
        "gender": "male",
        "style": "normal",
        "voice": "echo",
        "speed": 0.7,
    },
    "meals": {
        "gender": "male",
        "style": "normal",
        "voice": "echo",
        "speed": 0.7,
    },
    "social": {
        "gender": "female",
        "style": "cheerful, higher",
        "voice": "nova",
        "speed": 1.5,
    },
    "leisure": {
        "gender": "male",
        "style": "soft, slow",
        "voice": "echo",
        "speed": 0.7,
    },
    "therapy": {
        "gender": "male",
        "style": "soft, slow",
        "voice": "echo",
        "speed": 0.8,
    },
    "urgent": {
        "gender": "male",
        "style": "deep, fast, firm",
        "voice": "onyx",
        "speed": 1.1,
    },
    "common": {
        "gender": "male",
        "style": "default",
        "voice": "alloy",
        "speed": 1.1,
    }
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

    def generate_voice_reminder(self, text: str, category: str) -> Optional[bytes]:
        """
        Generates an audio stream from text using OpenAI TTS.
        """
        if not self.api_key:
            log_debug("tts_error", {"error": "OpenAI API Key missing"})
            return None

        cat = category.lower() if category else "common"
        profile = VOICE_PROFILES.get(cat, VOICE_PROFILES["common"])
        
        voice = profile["voice"]
        speed = profile["speed"]

        payload = {
            "model": "tts-1",
            "input": text,
            "voice": voice,
            "speed": speed
        }

        try:
            response = requests.post(self.url, headers=self._headers(), json=payload, timeout=30)
            response.raise_for_status()
            
            return response.content
        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg:
                log_debug("tts_forbidden", {"error": error_msg, "text": text, "model": "tts-1"})
            else:
                log_debug("tts_api_error", {"error": error_msg, "text": text})
            return None

voice_service = VoiceService()
