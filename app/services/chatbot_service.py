from __future__ import annotations
from pathlib import Path
from app.core.config import settings


class ChatbotService:
    def __init__(self):
        self.pipeline = None
        self._load_emotion_model()

    def _load_emotion_model(self):
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
        except Exception as e:
            print("❌ transformers import failed:", e)
            self.pipeline = None
            return

        model_dir = Path(settings.EMOTION_MODEL_DIR).resolve()
        print("🔎 Emotion model dir:", model_dir)

        if not model_dir.exists():
            print(f"❌ Emotion model directory not found: {model_dir}")
            self.pipeline = None
            return

        try:
            # ✅ Check for weights before loading to avoid HF errors
            weights_bin = model_dir / "pytorch_model.bin"
            weights_safe = model_dir / "model.safetensors"
            
            if not (weights_bin.exists() or weights_safe.exists()):
                print(f"⚠️ Emotion model weights missing in {model_dir}. Prediction will use default 'neutral'.")
                self.pipeline = None
                return

            # ✅ local_files_only prevents HF repo-id confusion
            tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
            model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), local_files_only=True)

            self.pipeline = pipeline(
                "text-classification",
                model=model,
                tokenizer=tokenizer,
                top_k=1,
            )
            print("✅ Emotion model loaded successfully!")
        except Exception as e:
            print("❌ Failed to load emotion model:", e)
            self.pipeline = None

    def predict_emotion(self, text: str) -> str:
        if not text or not text.strip():
            return "neutral"

        if self.pipeline is None:
            return "neutral"

        try:
            out = self.pipeline(text)
            label = out[0][0]["label"]
            return str(label).lower()
        except Exception as e:
            print("❌ Emotion prediction failed:", e)
            return "neutral"

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
                timeout=20.0,
            )

            result = response.query_result
            return {
                "intent": result.intent.display_name if result.intent else None,
                "reply": result.fulfillment_text or "",
            }
        except Exception as e:
            print(f"❌ Dialogflow Error (Project: {settings.DIALOGFLOW_PROJECT_ID}): {e}")
            return {"intent": None, "reply": ""}

    def chat(self, message: str, session_id: str):
        # ✅ emotion of elder/user message
        user_emotion = self.predict_emotion(message)

        # dialog / bot reply
        df = self.dialogflow_detect_intent(message, session_id)
        reply = df.get("reply") or "Would you like to tell me more?"
        intent = df.get("intent")

        return reply, user_emotion, intent