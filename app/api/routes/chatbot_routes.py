# app/api/routes/chatbot_routes.py

from fastapi import APIRouter, Request
from pydantic import BaseModel
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

from app.services.firestore_chat_store import (
    save_message,
    list_emotions_across_sessions,
)

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

# --------- Optional: file-based chat logs (local) ---------
CHAT_LOG_DIR = Path(__file__).resolve().parents[2] / "chat_logs"
CHAT_LOG_DIR.mkdir(parents=True, exist_ok=True)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    emotion: str
    intent: str | None
    session_id: str


def append_to_history(
    session_id: str,
    user_msg: str,
    bot_msg: str,
    emotion: str,
    intent: str | None
):
    log_file = CHAT_LOG_DIR / f"session_{session_id}.txt"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{ts}]\n")
        f.write(f"User: {user_msg}\n")
        f.write(f"Bot: {bot_msg}\n")
        f.write(f"Emotion: {emotion}\n")
        f.write(f"Intent: {intent if intent else 'none'}\n")
        f.write("\n")


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    session_id = req.session_id or str(uuid.uuid4())
    svc = request.app.state.chatbot_service

    # 1) Save USER message to Firestore
    save_message(
        session_id=session_id,
        sender="user",
        text=req.message
    )

    # 2) Get bot response (Dialogflow/ML)
    reply, emotion, intent = svc.chat(req.message, session_id)

    # 3) Save BOT message to Firestore
    save_message(
        session_id=session_id,
        sender="bot",
        text=reply,
        emotion=emotion,
        intent=intent
    )

    # 4) (Optional) Save to local file logs too
    append_to_history(session_id, req.message, reply, emotion, intent)

    return ChatResponse(
        reply=reply,
        emotion=emotion,
        intent=intent,
        session_id=session_id
    )


@router.get("/history/{session_id}")
def history(session_id: str, days: int = 7):
    """
    days=7  -> last 7 days
    days=0  -> all messages
    """
    db = firestore.client()
    session_ref = db.collection("chat_sessions").document(session_id)

    q = session_ref.collection("messages")

    # Filter by time only if days > 0
    if days > 0:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q = q.where("createdAt", ">=", since)

    docs = q.order_by("createdAt").stream()

    out = []
    for d in docs:
        data = d.to_dict() or {}
        data["id"] = d.id

        ts = data.get("createdAt")
        # Firestore Timestamp has .datetime
        if ts is not None and hasattr(ts, "datetime"):
            data["createdAtIso"] = ts.datetime.replace(
                tzinfo=timezone.utc
            ).isoformat()

        out.append(data)

    # IMPORTANT: do NOT return 404
    return {"session_id": session_id, "messages": out}


@router.get("/sessions")
def sessions(limit: int = 50):
    """
    Lists chat sessions ordered by updatedAt desc.
    """
    db = firestore.client()

    docs = (
        db.collection("chat_sessions")
        .order_by("updatedAt", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )

    out = []
    for d in docs:
        data = d.to_dict() or {}
        out.append({
            "session_id": d.id,
            "createdAt": data.get("createdAt"),
            "updatedAt": data.get("updatedAt"),
        })

    return {"sessions": out}


@router.get("/emotions")
def emotions(days: int = 7, limit: int = 500):
    """
    Returns emotions across sessions (for last N days).
    Requires list_emotions_across_sessions() in firestore_chat_store.py
    """
    items = list_emotions_across_sessions(days=days, limit=limit)
    return {"days": days, "items": items}
