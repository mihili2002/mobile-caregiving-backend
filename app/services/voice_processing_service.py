import os
import requests
from typing import Optional

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"

class VoiceProcessingService:
    def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribes audio bytes into text using OpenAI Whisper API.
        """
        if not OPENAI_API_KEY:
            return "ERROR: OpenAI API Key missing"

        # Whisper requires a file-like object with a filename (e.g., .wav, .mp3)
        # We can use a temporary file or just a named tuple for the multipart request.
        files = {
            "file": ("audio.wav", audio_bytes, "audio/wav"),
            "model": (None, "whisper-1"),
        }
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        }

        try:
            response = requests.post(OPENAI_WHISPER_URL, headers=headers, files=files, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get("text", "")
        except Exception as e:
            print(f"Transcription Error: {e}")
            return f"ERROR: Transcription failed. {str(e)}"

voice_processing_service = VoiceProcessingService()
