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
print(f"Testing access to Dialogflow Project: {project_id}")

try:
    print("Attempting to list intents (verifying permissions)...")
    client = dialogflow.IntentsClient()
    parent = f"projects/{project_id}/agent"
    intents = client.list_intents(request={"parent": parent}, timeout=30.0)
    
    intent_names = [intent.display_name for intent in intents]
    print(f"✅ SUCCESS! Found {len(intent_names)} intents: {intent_names[:5]}...")
    
except Exception as e:
    print(f"❌ FAILED to list intents: {e}")

try:
    print("\nAttempting to detect intent (verifying session flow)...")
    session_client = dialogflow.SessionsClient()
    session = session_client.session_path(project_id, "test-session-diag")
    text_input = dialogflow.TextInput(text="hello", language_code="en")
    query_input = dialogflow.QueryInput(text=text_input)
    
    response = session_client.detect_intent(
        request={"session": session, "query_input": query_input},
        timeout=30.0
    )
    print(f"✅ SUCCESS! Reply: '{response.query_result.fulfillment_text}'")
    
except Exception as e:
    print(f"❌ FAILED to detect intent: {e}")
