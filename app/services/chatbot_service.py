from __future__ import annotations
from pathlib import Path
from app.core.config import settings


class ChatbotService:

    def __init__(self):
        self.pipeline = None
        self.nlp = None  # IMPORTANT: always define first

        self._init_nlp_service()
        self._load_emotion_model()

    # ===============================
    # INIT NLP SERVICE
    # ===============================
    def _init_nlp_service(self):
        try:
            from app.services.nlp_service import NLPService
            self.nlp = NLPService()
            print("✅ NLPService initialized")
        except Exception as e:
            print("❌ NLPService import failed:", repr(e))
            self.nlp = None

    # ===============================
    # LOAD EMOTION MODEL
    # ===============================
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
            weights_bin = model_dir / "pytorch_model.bin"
            weights_safe = model_dir / "model.safetensors"

            if not (weights_bin.exists() or weights_safe.exists()):
                print(f"⚠️ Emotion model weights missing in {model_dir}")
                self.pipeline = None
                return

            tokenizer = AutoTokenizer.from_pretrained(
                str(model_dir),
                local_files_only=True
            )

            model = AutoModelForSequenceClassification.from_pretrained(
                str(model_dir),
                local_files_only=True
            )

            self.pipeline = pipeline(
                "text-classification",
                model=model,
                tokenizer=tokenizer,
                top_k=1
            )

            print("✅ Emotion model loaded successfully!")

        except Exception as e:
            print("❌ Failed to load emotion model:", e)
            self.pipeline = None

    # ===============================
    # EMOTION PREDICTION
    # ===============================
    def predict_emotion(self, text: str) -> str:

        if not text or not text.strip():
            return "neutral"

        text_lower = text.lower()

        if "wonder" in text_lower or "wondered" in text_lower:
            return "surprise"

        if self.pipeline is None:
            return "neutral"

        try:
            out = self.pipeline(text)
            label = out[0][0]["label"].lower()

            if label in ["joy", "happy"]:
                return "happy"
            if label in ["sad", "sadness"]:
                return "sad"
            if label in ["anger", "angry"]:
                return "anger"
            if label in ["fear"]:
                return "fear"
            if label in ["surprise", "surprised"]:
                return "surprise"
            if label in ["disgust"]:
                return "disgust"

            return label

        except Exception as e:
            print("❌ Emotion prediction failed:", e)
            return "neutral"

    # ===============================
    # DIALOGFLOW INTENT
    # ===============================
    def dialogflow_detect_intent(self, text: str, session_id: str):

        try:
            from google.cloud import dialogflow_v2 as dialogflow
        except Exception:
            return {"intent": None, "reply": ""}

        try:
            client = dialogflow.SessionsClient()

            project_id = settings.DIALOGFLOW_PROJECT_ID
            language_code = getattr(settings, "DIALOGFLOW_LANGUAGE_CODE", "en")

            session = client.session_path(project_id, session_id)

            text_input = dialogflow.TextInput(
                text=text,
                language_code=language_code
            )

            query_input = dialogflow.QueryInput(text=text_input)

            response = client.detect_intent(
                request={
                    "session": session,
                    "query_input": query_input
                },
                timeout=20.0
            )

            result = response.query_result

            return {
                "intent": result.intent.display_name if result.intent else None,
                "reply": result.fulfillment_text or ""
            }

        except Exception as e:
            print(f"❌ Dialogflow Error: {e}")
            return {"intent": None, "reply": ""}

    # ===============================
    # CHAT FUNCTION (FIXED INDENTATION)
    # ===============================
    def chat(self, message: str, session_id: str):

        # -----------------------------
        # 1. SAFETY CHECK
        # -----------------------------
        if self.nlp and hasattr(self.nlp, "detect_emergency"):
            try:
                if self.nlp.detect_emergency(message):
                    return (
                        "⚠ Emergency detected! Please contact caregiver immediately.",
                        "emergency",
                        "emergency"
                    )
            except Exception as e:
                print("❌ Emergency check failed:", e)

        # -----------------------------
        # 2. DIALOGFLOW
        # -----------------------------
        df = self.dialogflow_detect_intent(message, session_id)

        reply = df.get("reply")
        intent = df.get("intent")

        # -----------------------------
        # 3. FALLBACK NLP
        # -----------------------------
        if not reply or reply.strip() == "":
            if self.nlp and hasattr(self.nlp, "call_free_nlp_api"):
                try:
                    reply = self.nlp.call_free_nlp_api(message)
                except Exception:
                    reply = "I'm here for you. Can you tell me more?"
            else:
                reply = "I'm here for you. Can you tell me more?"

            intent = "fallback_nlp"

        # -----------------------------
        # 4. EMOTION
        # -----------------------------
        emotion = self.predict_emotion(message)

        return reply, emotion, intent