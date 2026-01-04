# app/api/routes/chatbot_routes.py

from fastapi import APIRouter, Request, Header, HTTPException
from pydantic import BaseModel
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone

from firebase_admin import auth, firestore

from app.core.firebase import init_firebase
from app.services.emotion_report import export_session_emotions_to_txt

from app.services.firestore_chat_store import (
    save_message,
    list_emotions_without_collection_group,
    list_user_emotions_in_range_without_collection_group,  # ✅ NEW
)

from app.services.mood_summary import summarize_emotions  # ✅ NEW

from fastapi.responses import FileResponse

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


# ---------- History Q&A (existing) ----------
class HistoryQARequest(BaseModel):
    session_id: str
    question: str
    max_messages: int = 40


class HistoryQAResponse(BaseModel):
    answer: str
    session_id: str


def append_to_history(
    session_id: str,
    user_msg: str,
    bot_msg: str,
    emotion: str,
    intent: str | None,
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


def _get_uid_from_request(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization: Bearer <token>")

    token = authorization.split("Bearer ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty bearer token")

    try:
        init_firebase()
        # ✅ tolerate small clock drift
        decoded = auth.verify_id_token(token, clock_skew_seconds=60)
        return decoded["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid/expired token: {e}")


def _get_session_messages(uid: str, session_id: str, max_messages: int = 40):
    init_firebase()
    db = firestore.client()

    session_ref = (
        db.collection("users")
        .document(uid)
        .collection("chat_sessions")
        .document(session_id)
    )

    docs = (
        session_ref.collection("messages")
        .order_by("createdAt", direction=firestore.Query.DESCENDING)
        .limit(max_messages)
        .stream()
    )

    items = []
    for d in docs:
        items.append(d.to_dict() or {})

    items.reverse()
    return items


def _build_context(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        sender = (m.get("sender") or "").lower()
        text = (m.get("text") or "").strip()
        if not text:
            continue

        if sender == "user":
            lines.append(f"Elder: {text}")
        else:
            lines.append(f"Bot: {text}")

    return "\n".join(lines)


# ✅ NEW: detect emotion requested in the question (emoji or word)
def _detect_requested_emotion(text: str) -> str | None:
    t = (text or "")

    # Emoji -> emotion
    emoji_map = {
        "😊": "joy",
        "😀": "joy",
        "😄": "joy",
        "🙂": "joy",
        "😢": "sadness",
        "😭": "sadness",
        "☹": "sadness",
        "🙁": "sadness",
        "😡": "anger",
        "😠": "anger",
        "🤬": "anger",
        "😨": "fear",
        "😰": "fear",
        "😟": "fear",
        "😱": "fear",
        "😐": "neutral",
        "😶": "neutral",
        "😑": "neutral",
    }
    for emj, emo in emoji_map.items():
        if emj in t:
            return emo

    # Word -> emotion (case-insensitive)
    low = t.lower()
    word_map = {
        "happy": "joy",
        "joy": "joy",
        "sad": "sadness",
        "sadness": "sadness",
        "angry": "anger",
        "anger": "anger",
        "mad": "anger",
        "fear": "fear",
        "anxious": "fear",
        "anxiety": "fear",
        "neutral": "neutral",
        "calm": "neutral",
    }
    for w, emo in word_map.items():
        if w in low:
            return emo

    return None


# ✅ NEW: decide the time range from the question (UTC)
def _range_from_question_utc(q: str):
    text = (q or "").lower()

    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    if "today" in text:
        return today_start, today_start + timedelta(days=1)

    if "yesterday" in text:
        return today_start - timedelta(days=1), today_start

    if "week" in text or "last 7 days" in text:
        return today_start - timedelta(days=7), today_start + timedelta(days=1)

    # fallback = yesterday
    return today_start - timedelta(days=1), today_start


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, authorization: str | None = Header(default=None)):
    uid = _get_uid_from_request(authorization)

    session_id = req.session_id or str(uuid.uuid4())
    svc = request.app.state.chatbot_service

    # 1) normal dialogflow + emotion model
    reply, emotion, intent = svc.chat(req.message, session_id)

    # ✅ 2) Override: Mood summary (supports emoji + specific emotion)
    msg = (req.message or "").lower()
    is_summary = ("summary" in msg or "summarize" in msg or "how was" in msg)
    is_emotion_question = ("mood" in msg or "emotion" in msg or "feel" in msg or "feeling" in msg)

    # If user is asking about mood/emotion summary (and time like today/yesterday/week)
    if intent == "mood.summary.yesterday" or (is_summary and is_emotion_question):
        start, end = _range_from_question_utc(req.message)
        requested_emotion = _detect_requested_emotion(req.message)  # ✅ emoji or word

        items = list_user_emotions_in_range_without_collection_group(
            uid=uid,
            start=start,
            end=end,
            limit=500,
            sessions_limit=80,
        )

        # ✅ summarize only that emotion if user asked for it
        reply = summarize_emotions(items, only_emotion=requested_emotion)
        intent = intent or "mood.summary"

    # 3) Save USER message with predicted emotion
    save_message(
        uid=uid,
        session_id=session_id,
        sender="user",
        text=req.message,
        emotion=emotion,
    )

    # 4) Save BOT message
    save_message(
        uid=uid,
        session_id=session_id,
        sender="bot",
        text=reply,
        intent=intent,
    )

    append_to_history(session_id, req.message, reply, emotion, intent)

    return ChatResponse(
        reply=reply,
        emotion=emotion,
        intent=intent,
        session_id=session_id,
    )


@router.get("/history/{session_id}")
def history(
    session_id: str,
    request: Request,
    days: int = 7,
    authorization: str | None = Header(default=None),
):
    uid = _get_uid_from_request(authorization)

    init_firebase()
    db = firestore.client()

    session_ref = (
        db.collection("users")
        .document(uid)
        .collection("chat_sessions")
        .document(session_id)
    )

    q = session_ref.collection("messages")

    if days > 0:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q = q.where("createdAt", ">=", since)

    docs = q.order_by("createdAt").stream()

    out = []
    for d in docs:
        data = d.to_dict() or {}
        data["id"] = d.id

        ts = data.get("createdAt")
        if ts is not None and hasattr(ts, "datetime"):
            data["createdAtIso"] = ts.datetime.replace(tzinfo=timezone.utc).isoformat()

        out.append(data)

    return {"session_id": session_id, "messages": out}


@router.get("/sessions")
def sessions(
    request: Request,
    limit: int = 50,
    authorization: str | None = Header(default=None),
):
    uid = _get_uid_from_request(authorization)

    init_firebase()
    db = firestore.client()

    docs = (
        db.collection("users")
        .document(uid)
        .collection("chat_sessions")
        .order_by("updatedAt", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )

    out = []
    for d in docs:
        data = d.to_dict() or {}
        out.append(
            {
                "session_id": d.id,
                "createdAt": data.get("createdAt"),
                "updatedAt": data.get("updatedAt"),
            }
        )

    return {"sessions": out}


@router.get("/emotions")
def emotions(
    request: Request,
    days: int = 7,
    limit: int = 500,
    authorization: str | None = Header(default=None),
):
    uid = _get_uid_from_request(authorization)

    items = list_emotions_without_collection_group(
        uid=uid,
        days=days,
        limit=limit,
        sessions_limit=50,
    )

    return {"days": days, "items": items}


@router.get("/emotions/session/{session_id}/export")
def export_session_emotions(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    uid = _get_uid_from_request(authorization)

    path = export_session_emotions_to_txt(
        uid=uid,
        session_id=session_id,
        out_dir=str(CHAT_LOG_DIR),
    )

    return FileResponse(
        path,
        filename=Path(path).name,
        media_type="text/plain",
    )


@router.post("/history_qa", response_model=HistoryQAResponse)
def history_qa(
    req: HistoryQARequest,
    request: Request,
    authorization: str | None = Header(default=None),
):
    uid = _get_uid_from_request(authorization)

    messages = _get_session_messages(
        uid=uid,
        session_id=req.session_id,
        max_messages=req.max_messages,
    )

    if not messages:
        return HistoryQAResponse(
            answer="I couldn't find any messages for that session.",
            session_id=req.session_id,
        )

    context = _build_context(messages)

    svc = request.app.state.chatbot_service
    answer = svc.answer_from_history(req.question, context)

    return HistoryQAResponse(
        answer=answer,
        session_id=req.session_id,
    )


@router.post("/history_qa_db")
def history_qa_db(
    req: HistoryQARequest,
    authorization: str | None = Header(default=None),
):
    uid = _get_uid_from_request(authorization)

    messages = _get_session_messages(uid, req.session_id, req.max_messages)
    if not messages:
        return {"answer": "No messages found for this session.", "session_id": req.session_id}

    # NOTE: _answer_from_db isn't defined in your pasted file; keep your existing logic here
    answer = _answer_from_db(req.question, messages)  # type: ignore
    return {"answer": answer, "session_id": req.session_id}
