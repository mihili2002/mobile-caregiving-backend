from fastapi import (
    APIRouter,
    Request,
    Header,
    HTTPException,
    UploadFile,
    File,
    Query,
)
from pydantic import BaseModel
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from google.api_core.exceptions import ResourceExhausted
from firebase_admin import firestore

from app.core.firebase import verify_id_token
from app.services.firestore_chat_store import (
    save_message_for_user,
    list_emotions_for_user,
    list_sessions_for_user,  # ✅ NEW
    delete_session_for_user, 
)


from app.services.firestore_journal_store import (
    create_journal_entry,
    list_journals_for_user,
    get_journal,
    delete_journal,
)

from app.services.journal_qa import pick_relevant_journals, build_context_snippet

import subprocess

from faster_whisper import WhisperModel

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

def _handle_firestore_quota_error(e: Exception):
    if isinstance(e, RuntimeError) and str(e) == "FIRESTORE_QUOTA_EXCEEDED":
        raise HTTPException(
            status_code=429,
            detail="Firestore quota exceeded. Please try again later.",
        )

# =========================================================
# Paths & limits
# =========================================================
BASE_DIR = Path(__file__).resolve().parents[3]
UPLOADS_DIR = BASE_DIR / "uploads"
JOURNAL_DIR = UPLOADS_DIR / "journals"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB
ALLOWED_EXTS = {".m4a", ".mp3", ".wav", ".webm", ".ogg"}

CHAT_LOG_DIR = BASE_DIR / "chat_logs"
CHAT_LOG_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# Whisper model (load once)
# =========================================================
WHISPER_MODEL = WhisperModel("base", device="cpu", compute_type="int8")


# =========================================================
# Models
# =========================================================
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    emotion: str
    intent: str | None
    session_id: str


class JournalCreateResponse(BaseModel):
    journal_id: str
    audioUrl: str


class JournalEmotionResponse(BaseModel):
    journal_id: str
    emotion: str | None = None
    emotion_confidence: float | None = None
    status: str


class JournalAskResponse(BaseModel):
    question_text: str
    reply_text: str
    session_id: str | None = None


# ✅ NEW: response for emotion trend
class EmotionTrendItem(BaseModel):
    journal_id: str
    created_at: str
    emotion: str | None = None
    confidence: float | None = None


class EmotionTrendResponse(BaseModel):
    elder_uid: str
    items: list[EmotionTrendItem]

class ChatSessionItem(BaseModel):
    session_id: str
    updatedAtIso: str | None = None
    createdAtIso: str | None = None
    lastMessage: str = ""
    lastSender: str = ""
    lastEmotion: str | None = None
    lastIntent: str | None = None


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionItem]

class ChatSessionDeleteResponse(BaseModel):
    session_id: str
    deleted: bool

# =========================================================
# Helpers
# =========================================================
def _uid_from_auth_header(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing/invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    decoded = verify_id_token(token)
    uid = decoded.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid token (no uid)")
    return uid


def _get_user_role(uid: str) -> str:
    db = firestore.client()
    doc = db.collection("users").document(uid).get()
    if not doc.exists:
        return ""
    return str((doc.to_dict() or {}).get("role") or "").lower()


def append_to_history(session_id: str, user_msg: str, bot_msg: str, emotion: str, intent: str | None):
    log_file = CHAT_LOG_DIR / f"session_{session_id}.txt"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{ts}]\n")
        f.write(f"User: {user_msg}\n")
        f.write(f"Bot: {bot_msg}\n")
        f.write(f"Emotion: {emotion}\n")
        f.write(f"Intent: {intent or 'none'}\n\n")


def _convert_to_wav(src_path: Path, sample_rate: int = 16000) -> Path:
    wav_path = src_path.with_suffix(".wav")
    cmd = [
        "ffmpeg", "-y", "-i", str(src_path),
        "-vn", "-ac", "1", "-ar", str(sample_rate), str(wav_path),
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="ffmpeg not found.")
    except subprocess.CalledProcessError:
        raise HTTPException(status_code=500, detail="Audio conversion failed (ffmpeg error).")
    return wav_path


def _transcribe_wav(wav_path: Path) -> tuple[str, str | None, float | None]:
    segments, info = WHISPER_MODEL.transcribe(str(wav_path))
    parts = []
    for seg in segments:
        t = (seg.text or "").strip()
        if t:
            parts.append(t)
    transcript = " ".join(parts).strip()
    language = getattr(info, "language", None)
    return transcript, language, None


def _journal_audio_fs_path(uid: str, audio_path: str | None) -> Path | None:
    if not audio_path:
        return None
    return UPLOADS_DIR / audio_path


def _update_journal_emotion_in_firestore(uid: str, journal_id: str, emotion: str, emotion_conf: float | None):
    db = firestore.client()
    ref = db.collection("users").document(uid).collection("journals").document(journal_id)
    ref.set(
        {
            "emotion": emotion,
            "emotionConfidence": emotion_conf,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def _parse_dt_from_journal(j: dict) -> datetime | None:
    """
    Your list_journals_for_user returns timestamps in different fields sometimes.
    We'll try a few fields safely and return UTC datetime.
    """
    candidates = [
        j.get("createdAtIso"),
        j.get("displayTime"),
        j.get("createdAt"),
        j.get("updatedAtIso"),
    ]
    for ts in candidates:
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def _is_allowed_elder_access(requester_uid: str, target_uid: str) -> None:
    if target_uid == requester_uid:
        return
    role = _get_user_role(requester_uid)
    if role not in {"caregiver", "doctor", "therapist", "admin"}:
        raise HTTPException(status_code=403, detail="Not allowed")


# =========================================================
# Chat APIs
# =========================================================
@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, authorization: str | None = Header(default=None)):
    uid = _uid_from_auth_header(authorization)
    session_id = req.session_id or str(uuid.uuid4())
    svc = request.app.state.chatbot_service

    save_message_for_user(uid, session_id, "user", req.message)
    reply, emotion, intent = svc.chat(req.message, session_id)
    save_message_for_user(uid, session_id, "bot", reply, emotion, intent)
    append_to_history(session_id, req.message, reply, emotion, intent)

    return ChatResponse(reply=reply, emotion=emotion, intent=intent, session_id=session_id)


@router.get("/sessions", response_model=ChatSessionListResponse)
def sessions(
    limit: int = Query(50, ge=1, le=200),
    authorization: str | None = Header(default=None),
):
    uid = _uid_from_auth_header(authorization)
    items = list_sessions_for_user(uid=uid, limit=limit) or []
    return {"items": items}

@router.get("/emotions")
def emotions(
    days: int = 7,
    limit: int = 500,
    elder_uid: str | None = None,
    authorization: str | None = Header(default=None),
):
    requester_uid = _uid_from_auth_header(authorization)
    target_uid = elder_uid or requester_uid

    _is_allowed_elder_access(requester_uid, target_uid)

    items = list_emotions_for_user(uid=target_uid, days=days, limit=limit)
    return {"elder_uid": target_uid, "items": items}


@router.get("/history/{uid}")
def get_chat_history(
    uid: str,
    days: int = Query(0, ge=0),
    authorization: str | None = Header(default=None),
):
    """
    Returns full chat history for a user (across all sessions) or filtered by days.
    Matches the expectation of the mood_summary.py/Flutter frontend.
    """
    _uid_from_auth_header(authorization) # Verify auth
    
    # We use the list_emotions_for_user logic but without the emotion filter 
    # if we want full history, or we can just reuse it if the frontend only cares about emotions.
    # Looking at mood_summary.dart: it says "EMOTION HISTORY" and "messages" list.
    # It filters for messages WITH emotion in the dart code too.
    
    from app.services.firestore_chat_store import list_emotions_for_user
    messages = list_emotions_for_user(uid=uid, days=days, limit=100)
    
    return {"messages": messages}


def filter_journals_by_date_keyword(question_text: str, journals: list):
    question = (question_text or "").lower()
    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)
    last_week_start = today - timedelta(days=7)
    results = []

    for j in journals:
        ts = j.get("createdAtIso") or j.get("displayTime")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            journal_date = dt.date()
        except Exception:
            continue

        if "today" in question and journal_date == today:
            results.append(j)
        elif "yesterday" in question and journal_date == yesterday:
            results.append(j)
        elif "last week" in question and last_week_start <= journal_date <= today:
            results.append(j)

    return results


# =========================================================
# JOURNAL Q&A (VOICE QUESTION -> JOURNAL-AWARE ANSWER)
# =========================================================
@router.post("/journals/ask", response_model=JournalAskResponse)
async def ask_journals_by_voice(
    request: Request,
    audio: UploadFile = File(...),
    elder_uid: str | None = None,
    authorization: str | None = Header(default=None),
):
    requester_uid = _uid_from_auth_header(authorization)
    target_uid = elder_uid or requester_uid

    _is_allowed_elder_access(requester_uid, target_uid)

    ext = Path(audio.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    q_dir = UPLOADS_DIR / "journal_questions" / target_uid
    q_dir.mkdir(parents=True, exist_ok=True)

    q_filename = f"{uuid.uuid4()}{ext}"
    q_path = q_dir / q_filename

    size = 0
    with q_path.open("wb") as f:
        while True:
            chunk = await audio.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_AUDIO_BYTES:
                f.close()
                q_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Audio file too large")
            f.write(chunk)

    wav_path = q_path
    if wav_path.suffix.lower() != ".wav":
        wav_path = _convert_to_wav(q_path, sample_rate=16000)

    question_text, lang, conf = _transcribe_wav(wav_path)

    if not question_text.strip():
        raise HTTPException(status_code=400, detail="Could not transcribe question")

    journals = list_journals_for_user(uid=target_uid, limit=50)
    selected = filter_journals_by_date_keyword(question_text, journals)

    if not selected:
        selected = pick_relevant_journals(question_text, journals, k=5)
    if not selected:
        selected = [j for j in journals if (j.get("transcript") or "").strip()][:5]

    context = build_context_snippet(selected)

    if not context.strip():
        return JournalAskResponse(
            question_text=question_text,
            reply_text="I don't have any journal entries for that time period.",
            session_id=str(uuid.uuid4()),
        )

    from openai import OpenAI
    client = OpenAI()
    session_id = str(uuid.uuid4())

    prompt = (
        "You are an emotional wellness assistant.\n"
        "Summarize the user's overall emotional state clearly.\n"
        "Base your answer strictly on the journal entries below.\n"
        "Mention emotional trends if multiple entries exist.\n"
        "Do NOT ask follow-up questions.\n\n"
        f"JOURNAL ENTRIES:\n{context}\n\n"
        f"USER QUESTION:\n{question_text}\n"
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You analyze journal entries and answer strictly based on them."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    reply_text = response.choices[0].message.content.strip()

    return JournalAskResponse(
        question_text=question_text,
        reply_text=reply_text,
        session_id=session_id,
    )


# =========================================================
# ✅ NEW ENDPOINT: Emotion fluctuation (for graph page)
# =========================================================
@router.get("/journals/emotion-trend", response_model=EmotionTrendResponse)
def journals_emotion_trend(
    request: Request,
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(500, ge=1, le=2000),
    elder_uid: str | None = Query(default=None),
    auto_fill_missing: bool = Query(default=False),
    authorization: str | None = Header(default=None),
):
    """
    Returns journal emotions for the last N days.
    - If no journals exist: returns {"items": []} (NOT 404) so UI can show "No data".
    - If auto_fill_missing=True: will run emotion predictor for journals missing emotion.
      (Can be expensive; keep false by default.)
    """
    requester_uid = _uid_from_auth_header(authorization)
    target_uid = elder_uid or requester_uid

    _is_allowed_elder_access(requester_uid, target_uid)

    since = datetime.now(timezone.utc) - timedelta(days=days)

    journals = list_journals_for_user(uid=target_uid, limit=limit) or []

    # filter by date
    filtered: list[dict] = []
    for j in journals:
        dt = _parse_dt_from_journal(j)
        if dt and dt >= since:
            filtered.append(j)

    # sort by time
    filtered.sort(key=lambda x: _parse_dt_from_journal(x) or datetime.min.replace(tzinfo=timezone.utc))

    # optional: compute missing emotions
    if auto_fill_missing:
        predictor = getattr(request.app.state, "emotion_predictor", None)
        for j in filtered:
            if (j.get("emotion") is not None) or (predictor is None):
                continue

            journal_id = j.get("journalId") or j.get("id") or j.get("journal_id")
            if not journal_id:
                continue

            # fetch full item to get audioPath + transcript reliably
            item = get_journal(target_uid, journal_id)
            if not item:
                continue

            audio_path = (item or {}).get("audioPath")
            fs_path = _journal_audio_fs_path(target_uid, audio_path)
            if not fs_path or not fs_path.exists():
                continue

            wav_path = fs_path
            if wav_path.suffix.lower() != ".wav":
                wav_path = _convert_to_wav(fs_path, sample_rate=16000)

            try:
                transcript = (item or {}).get("transcript")
                emotion, emotion_conf = predictor.predict(
                    wav_path=wav_path,
                    transcript=transcript,
                )
                # update firestore + local dict so response includes it
                try:
                    _update_journal_emotion_in_firestore(target_uid, journal_id, emotion, emotion_conf)
                except Exception:
                    pass
                j["emotion"] = emotion
                j["emotionConfidence"] = emotion_conf
            except Exception:
                pass

    # build response items
    items: list[EmotionTrendItem] = []
    for j in filtered:
        journal_id = j.get("journalId") or j.get("id") or j.get("journal_id")
        if not journal_id:
            # fallback: try from audio path name, but better to have journalId in store
            journal_id = str(j.get("audioPath") or "")

        dt = _parse_dt_from_journal(j)
        created_at = (dt.isoformat().replace("+00:00", "Z")) if dt else ""

        items.append(
            EmotionTrendItem(
                journal_id=str(journal_id),
                created_at=created_at,
                emotion=(j.get("emotion") or None),
                confidence=(j.get("emotionConfidence") if isinstance(j.get("emotionConfidence"), (int, float)) else None),
            )
        )

    return EmotionTrendResponse(elder_uid=target_uid, items=items)


# =========================================================
# JOURNAL: AUDIO UPLOAD (CONVERT + TRANSCRIBE + EMOTION)
# =========================================================
@router.post("/journals/upload", response_model=JournalCreateResponse)
async def upload_journal_audio(
    request: Request,
    audio: UploadFile = File(...),
    durationSec: int | None = None,
    authorization: str | None = Header(default=None),
):
    uid = _uid_from_auth_header(authorization)

    ext = Path(audio.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    user_dir = JOURNAL_DIR / uid
    user_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4()}{ext}"
    dest_path = user_dir / filename

    # Save uploaded file
    size = 0
    with dest_path.open("wb") as f:
        while True:
            chunk = await audio.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_AUDIO_BYTES:
                f.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Audio file too large")
            f.write(chunk)

    base_url = str(request.base_url).rstrip("/")

    # Convert to wav
    stored_path = dest_path
    if stored_path.suffix.lower() != ".wav":
        stored_path = _convert_to_wav(dest_path, sample_rate=16000)

    # Transcribe
    transcript = None
    language = None
    confidence = None
    if stored_path.suffix.lower() == ".wav":
        transcript, language, confidence = _transcribe_wav(stored_path)

    # Emotion prediction (text-first, audio fallback)
    emotion = None
    emotion_conf = None
    predictor = getattr(request.app.state, "emotion_predictor", None)

    if predictor is not None:
        try:
            emotion, emotion_conf = predictor.predict(
                wav_path=stored_path,
                transcript=transcript,
            )
            print(f"EMOTION RESULT: {emotion} ({emotion_conf})")
        except Exception as e:
            print(f"Emotion prediction error: {e}")

    # Build URL
    audio_path = f"journals/{uid}/{stored_path.name}"
    audio_url = f"{base_url}/static/{audio_path}"

    journal_id = create_journal_entry(
        uid=uid,
        audio_url=audio_url,
        audio_path=audio_path,
        duration_sec=durationSec,
        transcript=transcript,
        source="mobile",
        language=language,
        stt_confidence=confidence,
        emotion=emotion,
        emotion_confidence=emotion_conf,
    )

    return JournalCreateResponse(journal_id=journal_id, audioUrl=audio_url)


# =========================================================
# JOURNAL: EMOTION TRACK (CLICK BUTTON -> RETURN EMOTION)
# =========================================================
@router.get("/journals/{journal_id}/emotion", response_model=JournalEmotionResponse)
def get_or_run_journal_emotion(
    journal_id: str,
    request: Request,
    run_if_missing: bool = True,
    authorization: str | None = Header(default=None),
):
    uid = _uid_from_auth_header(authorization)

    item = get_journal(uid, journal_id)
    if not item:
        raise HTTPException(status_code=404, detail="Journal not found")

    existing_emotion = (item or {}).get("emotion")
    existing_conf = (item or {}).get("emotionConfidence")

    if existing_emotion is not None:
        return JournalEmotionResponse(
            journal_id=journal_id,
            emotion=existing_emotion,
            emotion_confidence=existing_conf,
            status="ok",
        )

    if not run_if_missing:
        return JournalEmotionResponse(
            journal_id=journal_id,
            emotion=None,
            emotion_confidence=None,
            status="failed",
        )

    audio_path = (item or {}).get("audioPath")
    fs_path = _journal_audio_fs_path(uid, audio_path)

    if not fs_path or not fs_path.exists():
        return JournalEmotionResponse(
            journal_id=journal_id,
            emotion=None,
            emotion_confidence=None,
            status="missing_audio",
        )

    wav_path = fs_path
    if wav_path.suffix.lower() != ".wav":
        wav_path = _convert_to_wav(fs_path, sample_rate=16000)

    predictor = getattr(request.app.state, "emotion_predictor", None)
    if predictor is None:
        return JournalEmotionResponse(
            journal_id=journal_id,
            emotion=None,
            emotion_confidence=None,
            status="model_not_loaded",
        )

    try:
        transcript = (item or {}).get("transcript")
        emotion, emotion_conf = predictor.predict(
            wav_path=wav_path,
            transcript=transcript,
        )

        try:
            _update_journal_emotion_in_firestore(uid, journal_id, emotion, emotion_conf)
        except Exception:
            pass

        return JournalEmotionResponse(
            journal_id=journal_id,
            emotion=emotion,
            emotion_confidence=emotion_conf,
            status="ok",
        )
    except Exception:
        return JournalEmotionResponse(
            journal_id=journal_id,
            emotion=None,
            emotion_confidence=None,
            status="failed",
        )


# =========================================================
# JOURNAL CRUD
# =========================================================
@router.get("/journals")
def list_journals(limit: int = 50, authorization: str | None = Header(default=None)):
    uid = _uid_from_auth_header(authorization)
    try:
        items = list_journals_for_user(uid=uid, limit=limit)
        return {"items": items}
    except ResourceExhausted:
        # Firestore throttled you
        raise HTTPException(status_code=429, detail="Firestore quota exceeded. Reduce requests or use emulator.")


@router.get("/journals/{journal_id}")
def read_journal(journal_id: str, authorization: str | None = Header(default=None)):
    uid = _uid_from_auth_header(authorization)
    item = get_journal(uid, journal_id)
    if not item:
        raise HTTPException(status_code=404, detail="Journal not found")
    return item


@router.delete("/journals/{journal_id}")
def remove_journal(journal_id: str, authorization: str | None = Header(default=None)):
    uid = _uid_from_auth_header(authorization)
    ok = delete_journal(uid, journal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Journal not found")
    return {"deleted": True}


@router.get("/journals/test-emotion")
def test_emotion(request: Request, authorization: str | None = Header(default=None)):
    uid = _uid_from_auth_header(authorization)
    predictor = getattr(request.app.state, "emotion_predictor", None)

    if predictor is None:
        return {"status": "❌ Model not loaded"}

    return {"status": "✅ Model ready (text+audio combined)"}

    # Add near your models


# =========================================================
# CHAT SESSION DELETE
# =========================================================
@router.delete("/sessions/{session_id}", response_model=ChatSessionDeleteResponse)
def delete_chat_session(
    session_id: str,
    authorization: str | None = Header(default=None),
):
    uid = _uid_from_auth_header(authorization)

    ok = delete_session_for_user(uid, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")

    return ChatSessionDeleteResponse(
        session_id=session_id,
        deleted=True,
    )
