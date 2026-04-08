import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

from app.core.config import settings
from app.services.chatbot_service import ChatbotService

# Set GOOGLE_APPLICATION_CREDENTIALS manually for the test
df_key = PROJECT_ROOT / "keys" / "dialogflow.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(df_key)

print(f"Testing Dialogflow with Project: {settings.DIALOGFLOW_PROJECT_ID}")
print(f"Using Key: {df_key}")

svc = ChatbotService()
message = "I feel so happy today"
session_id = "test-session-123"

print(f"\nSending message: '{message}'")
reply, emotion, intent = svc.chat(message, session_id)

print(f"\nResponse:")
print(f"Reply:   {reply}")
print(f"Emotion: {emotion}")
print(f"Intent:  {intent}")

if reply == "Would you like to tell me more?":
    print("\n❌ FAILED: Still getting fallback response.")
else:
    print("\n✅ SUCCESS: Got a real response from Dialogflow!")
