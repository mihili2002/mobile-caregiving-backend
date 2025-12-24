# app/services/chatbot_service.py
import json
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
from google.cloud import dialogflow_v2 as dialogflow
from google.api_core.exceptions import GoogleAPICallError, PermissionDenied, DeadlineExceeded

from app.core.config import settings


class ChatbotService:
    def __init__(self):
        self._load_emotion_model()

    def _load_emotion_model(self):
        path = settings.EMOTION_MODEL_DIR

        tokenizer = AutoTokenizer.from_pretrained(path)
        model = AutoModelForSequenceClassification.from_pretrained(path)

        # ✅ With top_k=1, pipeline may return nested list: [[{...}]]
        self.pipeline = pipeline(
            "text-classification",
            model=model,
            tokenizer=tokenizer,
            top_k=1
        )

        with open(f"{path}/config.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        self.id2label = {int(k): v for k, v in config["id2label"].items()}

    def predict_emotion(self, text: str) -> str:
        if not text.strip():
            return "neutral"

        out = self.pipeline(text)

        # Handles outputs like:
        # 1) [{'label': 'LABEL_2', 'score': 0.9}]
        # 2) [[{'label': 'LABEL_2', 'score': 0.9}]]   (common with top_k=1)
        if isinstance(out, list) and len(out) > 0:
            first = out[0]

            if isinstance(first, list) and len(first) > 0:
                result = first[0]          # nested list case
            elif isinstance(first, dict):
                result = first             # normal case
            else:
                return "unknown"
        else:
            return "unknown"

        label = result.get("label", "")
        if not label:
            return "unknown"

        if label.startswith("LABEL_"):
            idx = int(label.split("_")[1])
            return self.id2label.get(idx, "unknown").lower()

        return label.lower()

    def dialogflow_detect_intent(self, text: str, session_id: str):
        """
        Calls Dialogflow safely.
        - Timeout prevents Postman hanging
        - Exceptions fallback so API doesn't return 500
        """
        try:
            client = dialogflow.SessionsClient()

            project_id = settings.DIALOGFLOW_PROJECT_ID
            language_code = getattr(settings, "DIALOGFLOW_LANGUAGE_CODE", "en")

            session = client.session_path(project_id, session_id)

            text_input = dialogflow.TextInput(text=text, language_code=language_code)
            query_input = dialogflow.QueryInput(text=text_input)

            response = client.detect_intent(
                request={"session": session, "query_input": query_input},
                timeout=5.0
            )

            result = response.query_result
            return {
                "intent": result.intent.display_name,
                "reply": result.fulfillment_text,
            }

        except (PermissionDenied, DeadlineExceeded, GoogleAPICallError) as e:
            print("Dialogflow failed:", repr(e))
            return {"intent": None, "reply": ""}

        except Exception as e:
            print("Unexpected Dialogflow error:", repr(e))
            return {"intent": None, "reply": ""}

    def chat(self, message: str, session_id: str):
        emotion = self.predict_emotion(message)

        df = self.dialogflow_detect_intent(message, session_id)

        if df.get("reply"):
            reply = df["reply"]
        else:
            reply = "Would you like to tell me more?"

        return reply, emotion, df.get("intent")
