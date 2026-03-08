import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

from app.core.config import settings
from google.cloud import dialogflow_v2 as dialogflow

# Set GOOGLE_APPLICATION_CREDENTIALS
df_key = PROJECT_ROOT / "keys" / "dialogflow.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(df_key)

project_id = settings.DIALOGFLOW_PROJECT_ID
print(f"Deep test with message: 'I feel so happy today'")

try:
    session_client = dialogflow.SessionsClient()
    session = session_client.session_path(project_id, "test-session-diag-2")
    text_input = dialogflow.TextInput(text="I feel so happy today", language_code="en")
    query_input = dialogflow.QueryInput(text=text_input)
    
    print("Sending request to Dialogflow (timeout=30s)...")
    response = session_client.detect_intent(
        request={"session": session, "query_input": query_input},
        timeout=30.0
    )
    
    result = response.query_result
    print(f"\n✅ SUCCESS!")
    print(f"Intent matched:  '{result.intent.display_name if result.intent else 'None'}'")
    print(f"Fulfillment Text: '{result.fulfillment_text}'")
    print(f"Confidence:       {result.intent_detection_confidence}")
    
    if not result.fulfillment_text:
        print("\n⚠️ WARNING: Dialogflow matched an intent but returned NO text response.")
        print("Check your Dialogflow agent console to ensure intents have 'Responses' defined.")

except Exception as e:
    print(f"\n❌ FAILED: {e}")
