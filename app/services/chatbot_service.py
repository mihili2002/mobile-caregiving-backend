# app/services/chatbot_service.py
from __future__ import annotations

from app.core.config import settings


class ChatbotService:
    def __init__(self):
        # ✅ Do NOT load any HF/transformers models at startup
        # self._load_emotion_model()   # ❌ COMMENTED to prevent HFValidationError
        pass

    # --------------------------------------------------
    # ❌ EMOTION MODEL LOADING DISABLED COMPLETELY
    # --------------------------------------------------
    # def _load_emotion_model(self):
    #     from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
    #     path = settings.EMOTION_MODEL_DIR
    #
    #     # ❌ THESE LINES CAUSED YOUR ERROR (Windows path treated as HF repo id):
    #     # tokenizer = AutoTokenizer.from_pretrained(path)
    #     # model = AutoModelForSequenceClassification.from_pretrained(path)
    #
    #     # self.pipeline = pipeline("text-classification", model=model, tokenizer=tokenizer, top_k=1)

    # --------------------------------------------------
    # ✅ SAFE FALLBACK EMOTION
    # --------------------------------------------------
    def predict_emotion(self, text: str) -> str:
        return "neutral"

    # --------------------------------------------------
    # ✅ DIALOGFLOW OPTIONAL (won't crash if missing)
    # --------------------------------------------------
    def dialogflow_detect_intent(self, text: str, session_id: str) -> dict:
        try:
            from google.cloud import dialogflow_v2 as dialogflow
        except Exception:
            return {"intent": None, "reply": ""}

        try:
            client = dialogflow.SessionsClient()

            project_id = settings.DIALOGFLOW_PROJECT_ID
            language_code = getattr(settings, "DIALOGFLOW_LANGUAGE_CODE", "en")

            session = client.session_path(project_id, session_id)

            text_input = dialogflow.TextInput(text=text, language_code=language_code)
            query_input = dialogflow.QueryInput(text=text_input)

            response = client.detect_intent(
                request={"session": session, "query_input": query_input},
                timeout=5.0,
            )

            result = response.query_result
            return {
                "intent": result.intent.display_name if result.intent else None,
                "reply": result.fulfillment_text or "",
            }
        except Exception:
            return {"intent": None, "reply": ""}

    # --------------------------------------------------
    # ✅ MAIN CHAT
    # --------------------------------------------------
    def chat(self, message: str, session_id: str):
        emotion = self.predict_emotion(message)
        df = self.dialogflow_detect_intent(message, session_id)

        reply = df.get("reply") or "Would you like to tell me more?"
        intent = df.get("intent")

        return reply, emotion, intent
