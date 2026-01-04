# app/services/chatbot_service.py
import json
import re
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
from google.cloud import dialogflow_v2 as dialogflow
from google.api_core.exceptions import GoogleAPICallError, PermissionDenied, DeadlineExceeded

from app.core.config import settings


class ChatbotService:
    def __init__(self):
        self._load_emotion_model()

    # ---------------- Emotion model ----------------
    def _load_emotion_model(self):
        path = settings.EMOTION_MODEL_DIR

        tokenizer = AutoTokenizer.from_pretrained(path)
        model = AutoModelForSequenceClassification.from_pretrained(path)

        # top_k=1 sometimes returns [[{...}]]
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

        if isinstance(out, list) and len(out) > 0:
            first = out[0]
            if isinstance(first, list) and len(first) > 0:
                result = first[0]
            elif isinstance(first, dict):
                result = first
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

    # ---------------- Dialogflow ----------------
    def dialogflow_detect_intent(self, text: str, session_id: str):
        """
        Calls Dialogflow safely.
        - Timeout prevents hanging
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

    # ---------------- Chat (existing) ----------------
    def chat(self, message: str, session_id: str):
        emotion = self.predict_emotion(message)

        df = self.dialogflow_detect_intent(message, session_id)

        if df.get("reply"):
            reply = df["reply"]
        else:
            reply = "Would you like to tell me more?"

        return reply, emotion, df.get("intent")

    # ---------------- History Q&A (NEW) ----------------
    def answer_from_history(self, question: str, context: str) -> str:
        """
        Q&A about past chats.
        Uses Dialogflow with injected history context.
        Falls back to simple keyword search if Dialogflow has no reply.

        IMPORTANT:
        - context can be long. We trim it to avoid huge requests.
        """

        q = (question or "").strip()
        if not q:
            return "Please ask a question."

        # Trim context (Dialogflow has payload limits)
        # Keep last ~2500 chars of history (usually enough for last few turns)
        ctx = (context or "").strip()
        if len(ctx) > 2500:
            ctx = ctx[-2500:]

        # Build a question prompt with explicit instruction
        injected = (
            "Use ONLY the conversation history below to answer the question. "
            "If the answer is not in the history, say: "
            "\"I don't know from the saved chats.\" \n\n"
            f"Conversation history:\n{ctx}\n\n"
            f"Question:\n{q}"
        )

        # Use a separate dialogflow session for QA to not mix with main chat session
        qa_session_id = f"historyqa-{abs(hash(q)) % 10_000_000}"

        df = self.dialogflow_detect_intent(injected, qa_session_id)

        if df.get("reply"):
            return df["reply"].strip()

        # Fallback (works even if DF doesn't answer)
        return self._fallback_history_search(q, ctx)

    def _fallback_history_search(self, question: str, context: str) -> str:
        """
        Simple non-AI fallback: finds relevant lines from context.
        Also supports a basic 'summary' request.
        """
        q = question.lower()

        lines = [ln.strip() for ln in context.splitlines() if ln.strip()]
        if not lines:
            return "I don't know from the saved chats."

        # Summary request
        if "summar" in q or "overview" in q or "summary" in q:
            tail = lines[-12:]
            return "Here are the last key messages from your saved chats:\n" + "\n".join(tail)

        # Keyword-based match
        stop = {"what", "when", "where", "which", "about", "talk", "said", "tell", "me", "please"}
        keywords = [w for w in re.findall(r"[a-zA-Z]{3,}", q) if w not in stop]
        if not keywords:
            keywords = re.findall(r"[a-zA-Z]{3,}", q)

        scored = []
        for ln in lines:
            text = ln.lower()
            score = sum(1 for k in keywords if k in text)
            if score > 0:
                scored.append((score, ln))

        scored.sort(key=lambda x: x[0], reverse=True)

        if not scored:
            return "I don't know from the saved chats."

        top = [ln for _, ln in scored[:6]]
        return "From your saved chats, these parts seem relevant:\n" + "\n".join(top)
