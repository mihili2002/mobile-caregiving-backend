# app/services/chatbot_service.py
from __future__ import annotations

import json
from pathlib import Path

from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

from app.core.config import settings


# ---------------- Dialogflow is OPTIONAL ----------------
try:
    from google.cloud import dialogflow_v2 as dialogflow  # Dialogflow ES
    from google.api_core.exceptions import GoogleAPICallError, PermissionDenied, DeadlineExceeded

    _DIALOGFLOW_AVAILABLE = True
except Exception:
    dialogflow = None
    GoogleAPICallError = PermissionDenied = DeadlineExceeded = Exception
    _DIALOGFLOW_AVAILABLE = False


class ChatbotService:
    def __init__(self):
        self.pipeline = None
        self.id2label: dict[int, str] = {}
        self._load_emotion_model()

    # ---------------- Emotion Model Loader ----------------
    def _load_emotion_model(self) -> None:
        """
        Loads emotion model from a LOCAL folder (preferred) or from a Hugging Face repo id.
        If missing/unauthorized, app still starts and emotion falls back to 'neutral'.
        """
        model_source = settings.EMOTION_MODEL_DIR

        try:
            p = Path(model_source)

            # If local folder exists, use it as a local model path
            if p.exists() and p.is_dir():
                model_source = str(p.resolve())

            tokenizer = AutoTokenizer.from_pretrained(model_source)
            model = AutoModelForSequenceClassification.from_pretrained(model_source)

            self.pipeline = pipeline(
                "text-classification",
                model=model,
                tokenizer=tokenizer,
                top_k=1,
            )

            # Try local config.json for id2label mapping (optional)
            cfg_path = (Path(model_source) / "config.json")
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                raw = cfg.get("id2label", {})
                self.id2label = {int(k): v for k, v in raw.items()}

            print(f"[OK] Emotion model loaded from: {model_source}")

        except Exception as e:
            self.pipeline = None
            self.id2label = {}
            print("[WARN] Emotion model not loaded. Using fallback emotion='neutral'.")
            print("       Reason:", repr(e))

    # ---------------- Emotion Prediction ----------------
    def predict_emotion(self, text: str) -> str:
        if not text.strip():
            return "neutral"

        # Fallback if model didn't load
        if self.pipeline is None:
            return "neutral"

        out = self.pipeline(text)

        # out may be:
        # 1) [{'label':'LABEL_2','score':...}]
        # 2) [[{'label':'LABEL_2','score':...}]]
        if isinstance(out, list) and out:
            first = out[0]
            if isinstance(first, list) and first:
                result = first[0]
            elif isinstance(first, dict):
                result = first
            else:
                return "neutral"
        else:
            return "neutral"

        label = result.get("label", "")
        if not label:
            return "neutral"

        if label.startswith("LABEL_"):
            try:
                idx = int(label.split("_")[1])
                return self.id2label.get(idx, "neutral").lower()
            except Exception:
                return "neutral"

        return str(label).lower()

    # ---------------- Dialogflow (Optional) ----------------
    def dialogflow_detect_intent(self, text: str, session_id: str) -> dict:
        if not _DIALOGFLOW_AVAILABLE:
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

        except (PermissionDenied, DeadlineExceeded, GoogleAPICallError) as e:
            print("[WARN] Dialogflow failed:", repr(e))
            return {"intent": None, "reply": ""}

        except Exception as e:
            print("[WARN] Unexpected Dialogflow error:", repr(e))
            return {"intent": None, "reply": ""}

    # ---------------- Main Chat ----------------
    def chat(self, message: str, session_id: str):
        emotion = self.predict_emotion(message)

        df = self.dialogflow_detect_intent(message, session_id)
        reply = df.get("reply") or "Would you like to tell me more?"
        intent = df.get("intent")

        return reply, emotion, intent
