from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Request
from pydantic import BaseModel
from typing import Optional, List
import traceback
from datetime import datetime, timedelta
from firebase_admin import firestore
import re

from app.models.schemas import ExtractionResponse, Medication
from app.services.openai_service import process_voice_with_llm, RECALL_SYSTEM_PROMPT, process_reschedule_conversation, reset_chat_session
from app.services.memory_engine import memory_engine
from app.services.time_utils import extract_time_range, is_last_time_query
from app.services.extractor import extract_medications
from app.services.task_state_service import (
    build_task_occurrence,
    log_task_event,
    mark_completed,
    mark_acknowledged,
    mark_in_progress,
    mark_snoozed,
    handle_task_skip,      # orchestrator — replaces direct mark_skipped() calls
    reschedule_task_time,
    update_task_in_schedule,
)
from app.services.reminder_engine import process_todays_schedules
from app.services.voice_processing_service import voice_processing_service
from app.services.strategy_service import get_reminder_strategy
from app.services.ml_inferences import predict_elder_risk
from app.core.firebase import get_db

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/predict_reminder_strategy")
async def predict_strategy(request: Request):
    try:
        data = await request.json()
        uid = data.get("uid")
        if not uid:
            raise HTTPException(status_code=400, detail="uid required")

        db = get_db()
        doc = db.collection("elder_profiles").document(uid).get()
        if not doc.exists:
            return get_reminder_strategy({"age": 70})

        profile_data = doc.to_dict()
        strategy_res = get_reminder_strategy(profile_data)
        return strategy_res
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict_task_risk")
async def get_task_risk(request: Request):
    """
    Returns AI insights for a specific task.
    Expects { "profile": {...}, "task": {"task_name": "...", "time": "..."} }
    """
    try:
        data = await request.json()
        profile = data.get("profile")
        if not profile:
            raise HTTPException(status_code=400, detail="profile required")

        risk_data = predict_elder_risk(profile)
        strategy_data = get_reminder_strategy(profile)
        strategy = strategy_data.get("strategy", {})

        insights = {
            "ai_completion_prob": 1.0 - risk_data.get("prediction_probability", 0.5),
            "ai_expected_delay": strategy.get("expected_delay_min", 0),
            "ai_predicted_retries": strategy.get("auto_retries_count", 1),
            "ai_predicted_snoozes": strategy.get("max_snoozes_allowed", 3),
            "ai_needs_escalation": strategy.get("caregiver_escalation_enabled", False),
        }

        return {"status": "success", "predictions": insights}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


class VoiceCommandRequest(BaseModel):
    text: str
    uid: str
    session_id: Optional[str] = None
    local_time: Optional[str] = None


class FCMTokenUpdate(BaseModel):
    uid: str
    fcm_token: str


class ProfileCreateRequest(BaseModel):
    uid: str
    name: Optional[str] = "User"
    age: Optional[int] = 65
    long_term_illness: Optional[str] = "No"

    sleep_well_1to5: Optional[int] = 3
    tired_day_1to5: Optional[int] = 3

    forget_recent_1to5: Optional[int] = 3
    difficulty_remember_tasks_1to5: Optional[int] = 3
    forget_take_meds_1to5: Optional[int] = 3
    tasks_harder_1to5: Optional[int] = 3

    lonely_1to5: Optional[int] = 3
    sad_anxious_1to5: Optional[int] = 3
    social_talk_1to5: Optional[int] = 3
    enjoy_hobbies_1to5: Optional[int] = 3

    comfortable_app_1to5: Optional[int] = 3
    reminders_helpful_1to5: Optional[int] = 3
    reminders_right_time_1to5: Optional[int] = 3
    reminders_preference: Optional[str] = "Gentle Voice"


class TaskActionRequest(BaseModel):
    uid: str
    date: str
    task_id: str
    actor: Optional[str] = "elder"         # "elder" | "caregiver"
    snooze_minutes: Optional[int] = 10
    reason: Optional[str] = None
    confirmed: Optional[bool] = False       # elder confirmed a policy-gated skip
    notify_caregiver: Optional[bool] = None # None = use policy default

class TaskSkipRequest(TaskActionRequest):
    reasons: List[str] = []
    skip_decision_by: Optional[str] = None
    caregiver_skip_note: Optional[str] = None

class ReviewSkipRequest(BaseModel):
    uid: str
    date: str
    task_id: str
    actor: str = "caregiver"

class TaskFollowupRequest(BaseModel):
    uid: str
    date: str
    task_id: str
    session_id: Optional[str] = None


# In-memory storage for pending confirmations
# In production, Redis or Firestore is better
pending_confirmations = {}

GREETINGS = [
    "Hi there! I'm Alex, your routine coach. How can I help you today?",
    "Hello! Alex here. Ready to plan your day?",
    "Good day! I'm Alex. What's on your mind?",
    "Hi! It's Alex. I'm here to help with your schedule or any memories.",
    "Hey! Alex is ready! How can I support you right now?"
]

pending_task_followups = {}
pending_skip_confirmations = {}  # session_id -> {uid, date, task_id, actor, reason}

# Greeting cache: uid -> {"date": "YYYY-MM-DD", "reply": "..."}
# Prevents calling OpenAI on every chatbot open — one greeting per user per day.
_greeting_cache: dict = {}


# ---------------------------------------------------------
# Reschedule validation helpers
# ---------------------------------------------------------

def _is_valid_reschedule_time(time_str: Optional[str]) -> bool:
    """
    Checks that the time string is a well-formed HH:MM value in 24-hour format
    (as produced by _to_24h in openai_service) and within a realistic clock range.
    """
    if not time_str:
        return False
    try:
        h, m = time_str.split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except (ValueError, AttributeError):
        return False


def _is_valid_reschedule_date(date_str: Optional[str], user_now: Optional[datetime] = None) -> bool:
    """
    Checks that the date string is ISO-formatted (YYYY-MM-DD) and not more than
    30 days in the past (a simple sanity guard; rescheduling to last week is a
    data error, not a user intent).
    """
    if not date_str:
        return False
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        now = user_now or datetime.now()
        # Allow dates from yesterday (timezone drift) up to 365 days in the future
        delta = (dt.date() - now.date()).days
        return -1 <= delta <= 365
    except ValueError:
        return False


def _validate_reschedule_result(
    llm_result: dict,
    followup_date: str,
    user_now: Optional[datetime] = None,
) -> tuple[bool, str]:
    """
    Backend-side validation of an LLM reschedule result.
    Treats the LLM output as untrusted.

    Returns:
        (ok: bool, reason: str)
        ok=True  → safe to commit
        ok=False → keep conversation alive; `reason` explains why
    """
    # Gate 1: explicit user confirmation
    if not llm_result.get("confirmed"):
        return False, "not_confirmed"

    # Gate 2: time must be present and well-formed
    if not _is_valid_reschedule_time(llm_result.get("time")):
        return False, "invalid_time"

    # Gate 3: period (AM/PM) must be present — guards against silent AM/PM flip
    if not llm_result.get("period") in ("AM", "PM"):
        return False, "missing_period"

    # Gate 4: date must be present and plausible
    # We accept the LLM date if given, otherwise fall back to the followup date.
    effective_date = llm_result.get("date") or followup_date
    if not _is_valid_reschedule_date(effective_date, user_now):
        return False, "invalid_date"

    return True, "ok"

def detect_task_action_intent(text: str):
    """
    Lightweight fallback detector.
    This is kept even after adding LLM action extraction so simple direct phrases still work.
    """
    t = text.lower().strip()

    if any(x in t for x in ["done", "i did it", "i took it", "mark it done", "finished it"]):
        return {"type": "complete", "task_ref": "current"}
    if any(x in t for x in ["okay", "ok", "i heard", "yes i know"]):
        return {"type": "acknowledge", "task_ref": "current"}
    if any(x in t for x in ["i am taking it now", "doing it now", "starting now"]):
        return {"type": "start", "task_ref": "current"}
    if "remind me later" in t:
        return {"type": "snooze", "task_ref": "current", "snooze_minutes": 10}
    if "skip" in t:
        return {"type": "skip", "task_ref": "current", "reason": "voice_skip"}
    if any(x in t for x in ["stop reminding me", "cancel reminder", "cancel this reminder"]):
        return {"type": "skip", "task_ref": "current", "reason": "reminder_cancelled"}
    return None


def get_target_date(day_str: str, user_now: Optional[datetime] = None) -> str:
    day_str = (day_str or "today").lower()
    now = user_now or datetime.now()

    if "today" in day_str:
        return now.strftime("%Y-%m-%d")
    if "tomorrow" in day_str:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, d in enumerate(days):
        if d in day_str:
            target_weekday = i
            current_weekday = now.weekday()
            days_ahead = target_weekday - current_weekday

            if days_ahead < 0:
                days_ahead += 7
            elif days_ahead == 0 and "next" in day_str:
                days_ahead = 7

            return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    return now.strftime("%Y-%m-%d")


def normalize_timing(t: str) -> str:
    if not t:
        return "unknown"

    x = t.strip().lower()
    if x in ["ac", "a.c", "before food", "before meal"]:
        return "before_meal"
    if x in ["pc", "p.c", "after food", "after meal"]:
        return "after_meal"
    if x in ["with food", "with meal"]:
        return "with_meal"
    if x in ["bedtime", "night", "nocte", "at night", "hs"]:
        return "bedtime"
    if x in ["morning", "mane", "in the morning"]:
        return "morning"
    if x in ["afternoon"]:
        return "afternoon"
    if x in ["evening"]:
        return "evening"
    if x in ["as needed", "sos", "attack", "prn"]:
        return "as_needed"

    allowed = {
        "before_meal",
        "after_meal",
        "with_meal",
        "bedtime",
        "morning",
        "afternoon",
        "evening",
        "as_needed",
        "unknown",
    }
    if x in allowed:
        return x

    return "unknown"


def parse_duration_days(text: Optional[str]) -> Optional[int]:
    if not text:
        return None

    t = text.lower()
    m = re.search(r"(\d+)\s*(day|week|month|d|w|m)", t)
    if not m:
        return None

    val = int(m.group(1))
    unit = m.group(2)

    if unit.startswith("w"):
        return val * 7
    if unit.startswith("m"):
        return val * 30

    return val


def clean_drug_prefix(name: str) -> str:
    return re.sub(r"^(tab|cap|syp|inj|susp|tab\.|cap\.|syp\.|inj\.)\s+", "", name, flags=re.I).strip()


def infer_task_type(task_name: str) -> str:
    lower_name = (task_name or "").lower()

    if any(word in lower_name for word in ["blood pressure", "doctor", "checkup", "health", "sugar"]):
        return "health"
    if any(word in lower_name for word in ["medicine", "tablet", "pill", "capsule", "medication", "dose", "aspirin"]):
        return "medication"
    if any(word in lower_name for word in ["meal", "breakfast", "lunch", "dinner", "snack", "eat", "food"]):
        return "meal"
    if any(word in lower_name for word in ["call", "visit", "friend", "social", "daughter", "son", "grandchild"]):
        return "social"
    if any(word in lower_name for word in ["nap", "sleep", "rest", "leisure", "relax"]):
        return "leisure"
    if any(word in lower_name for word in ["exercise", "therapy", "stretch", "walk", "physio", "breathing"]):
        return "therapy"
    
    return "common"


def get_schedule_doc_ref(db, uid: str, date_str: str):
    from app.services.time_utils import get_schedule_doc_id
    doc_id = get_schedule_doc_id(uid, date_str)
    return db.collection("schedules").document(doc_id)


def get_current_active_task(doc_data: dict):
    tasks = doc_data.get("tasks", [])
    active_tasks = [
        t for t in tasks
        if t.get("status") in [
            "scheduled",
            "upcoming",
            "reminder_triggered",
            "acknowledged",
            "snoozed",
            "in_progress",
        ]
    ]
    active_tasks.sort(key=lambda x: x.get("scheduledAt", ""))
    return active_tasks[0] if active_tasks else None


def apply_task_action(db, doc_ref, uid: str, action_data: dict):
    doc = doc_ref.get()
    if not doc.exists:
        return None, "I couldn't find a task for today yet."

    current_task = get_current_active_task(doc.to_dict())
    if not current_task:
        return None, "I couldn't find an active task to update right now."

    task_id = current_task["id"]
    action_type = action_data.get("type")

    if action_type == "complete":
        mark_completed(db, doc_ref, uid, task_id, actor="elder")
        return "complete", f"Okay, I marked {current_task['task_name']} as completed."

    if action_type == "acknowledge":
        mark_acknowledged(db, doc_ref, uid, task_id, actor="elder")
        return "acknowledge", f"Okay, I noted your reminder for {current_task['task_name']}."

    if action_type == "start":
        mark_in_progress(db, doc_ref, uid, task_id, actor="elder")
        return "start", f"Okay, I marked {current_task['task_name']} as in progress."

    if action_type == "snooze":
        mins = int(action_data.get("snooze_minutes", 10))
        mark_snoozed(db, doc_ref, uid, task_id, mins, actor="elder")
        return "snooze", f"Okay, I will remind you again in {mins} minutes."

    if action_type in ["skip", "cancel_reminder"]:
        reason = action_data.get("reason", "voice_skip")
        confirmed = bool(action_data.get("confirmed", False))

        skip_result = handle_task_skip(
            db=db,
            schedule_doc_ref=doc_ref,
            uid=uid,
            task_id=task_id,
            date=date,
            actor="elder",
            reason=reason,
            confirmed=confirmed,
        )

        if skip_result["status"] == "confirmation_required":
            return "skip_confirm", skip_result["message"]

        if skip_result["status"] == "blocked":
            return "skip_blocked", skip_result["message"]

        if skip_result.get("escalation", {}).get("notified"):
            return "skip", f"Okay, I marked {current_task['task_name']} as skipped and informed your caregiver."

        return "skip", f"Okay, I marked {current_task['task_name']} as skipped."

    if action_type == "repeat":
        return "repeat", f"Of course. Let me repeat the reminder for {current_task['task_name']}."

    if action_type == "caregiver_help":
        return "caregiver_help", f"Alright. I will note that you may need caregiver help for {current_task['task_name']}."

    return None, "I understood you wanted to update the task, but I wasn't sure how."


async def get_context_summary(uid: str, user_now: Optional[datetime] = None) -> str:
    """
    Fetches a summary of today's schedule to provide context for the LLM.
    """
    try:
        db = firestore.client()
        now = user_now or datetime.now()
        today = now.strftime("%Y-%m-%d")
        doc_ref = get_schedule_doc_ref(db, uid, today)
        doc = doc_ref.get()

        if not doc.exists:
            return "No tasks scheduled for today yet."

        data = doc.to_dict()
        tasks = data.get("tasks", [])
        if not tasks:
            return "The schedule for today is empty."

        summary = "Today's Schedule:\n"
        for t in tasks:
            status = t.get("status", "pending")
            task_name = t.get("task_name", "Task")
            time_str = t.get("time", "unknown time")
            summary += f"- {task_name} at {time_str} ({status})\n"

        return summary
    except Exception as e:
        return f"Error fetching context: {str(e)}"


@router.post("/prescriptions/extract", response_model=ExtractionResponse)
async def extract_prescription(elder_id: str = Form(...), file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        filename = file.filename or "prescription"
        content_type = file.content_type or ""

        extracted, method = extract_medications(file_bytes, filename, content_type)
        meds = extracted.get("medications", []) or []
        doc_raw_text = extracted.get("raw_text", "")

        validated = []
        for m in meds:
            m["timing"] = normalize_timing(str(m.get("timing", "")))

            if not m.get("frequency_per_day") and m.get("frequency_text"):
                f_text = str(m.get("frequency_text", "")).lower()
                if "od" in f_text:
                    m["frequency_per_day"] = 1
                elif "bd" in f_text:
                    m["frequency_per_day"] = 2
                elif "tds" in f_text or "tid" in f_text:
                    m["frequency_per_day"] = 3
                elif "qid" in f_text:
                    m["frequency_per_day"] = 4

            if not m.get("duration_days") and m.get("duration_text"):
                m["duration_days"] = parse_duration_days(m.get("duration_text"))

            s = m.get("strength")
            m["dosage"] = s or "unknown"
            m["drug_name"] = clean_drug_prefix(m.get("drug_name", ""))

            if not m.get("from_date"):
                m["from_date"] = datetime.now().strftime("%Y-%m-%d")

            if m.get("duration_days") and m.get("from_date"):
                try:
                    start_dt = datetime.strptime(m["from_date"], "%Y-%m-%d")
                    end_dt = start_dt + timedelta(days=m["duration_days"])
                    m["to_date"] = end_dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

            validated.append(Medication(**m))

        return ExtractionResponse(
            elder_id=elder_id,
            medications=validated,
            used_method=method,
            raw_text=doc_raw_text
        )
    except Exception as e:
        print(f"Prescription extraction API error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process_audio_command")
async def process_audio_command(
    uid: str = Form(...),
    session_id: Optional[str] = Form(None),
    local_time: Optional[str] = Form(None),
    file: UploadFile = File(...)
):
    """
    Handles audio files, transcribes them, and then processes
    the command exactly like the text-based endpoint.
    """
    try:
        audio_bytes = await file.read()
        text = voice_processing_service.transcribe(audio_bytes)

        if text.startswith("ERROR:"):
            return {
                "action": "reply",
                "reply": "I'm sorry, I couldn't understand the audio. Please try again.",
                "error": text,
            }

        voice_command_req = VoiceCommandRequest(
            text=text,
            uid=uid,
            session_id=session_id,
            local_time=local_time,
        )
        result = await process_voice_command(voice_command_req)

        if isinstance(result, dict):
            result["transcribed_text"] = text

        return result

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process_voice_command")
async def process_voice_command(req: VoiceCommandRequest):
    try:
        raw_text = req.text or ""
        text = raw_text.lower()
        uid = req.uid
        session_id = req.session_id or f"{uid}_default"

        from app.services.logger import log_debug

        db = firestore.client()
        log_debug("voice_input_received", {"text": text, "uid": uid})

        user_now = None
        if req.local_time:
            try:
                user_now = datetime.fromisoformat(req.local_time.replace("Z", "+00:00"))
            except Exception:
                pass

        # ---------------------------------------------------------
        # X. Pending task followups — OpenAI-powered reschedule conversation
        # ---------------------------------------------------------
        if session_id in pending_task_followups:
            followup = pending_task_followups[session_id]

            if followup["type"] == "reschedule_task" and followup["step"] == "llm_conversation":
                reschedule_session_id = f"{session_id}_reschedule_{followup['task_id']}"

                # ---------------------------------------------------
                # Version safety — bump the counter BEFORE the await.
                # We capture this turn's version locally; after the
                # LLM returns we check whether a newer turn arrived
                # while we were waiting.  If so, this response is stale
                # and must be discarded.
                # ---------------------------------------------------
                followup["version"] = followup.get("version", 1) + 1
                this_turn_version = followup["version"]

                llm_result = await process_reschedule_conversation(
                    text=raw_text,
                    task_name=followup["task_name"],
                    session_id=reschedule_session_id,
                    user_now=user_now,
                )

                # Check for stale response (a newer turn arrived during the await)
                current_followup = pending_task_followups.get(session_id)
                if (
                    current_followup is None
                    or current_followup.get("version", 1) != this_turn_version
                ):
                    log_debug("reschedule_stale_response_dropped", {
                        "this_turn_version": this_turn_version,
                        "current_version": current_followup.get("version") if current_followup else None,
                        "session_id": session_id,
                    })
                    # Return the most recent in-progress reply without acting on it
                    return {
                        "action": "reply",
                        "reply": llm_result["reply"],
                        "intent": "task_followup",
                    }

                if llm_result["intent"] == "task_rescheduled" and llm_result["time"]:
                    # ---------------------------------------------------
                    # Backend validation — never trust the LLM blindly
                    # ---------------------------------------------------
                    ok, reason = _validate_reschedule_result(
                        llm_result,
                        followup_date=followup["date"],
                        user_now=user_now,
                    )

                    if not ok:
                        log_debug("reschedule_validation_failed", {
                            "reason": reason,
                            "llm_result": llm_result,
                            "session_id": session_id,
                        })

                        # Map the failure reason to a user-friendly clarification prompt
                        _clarify = {
                            "not_confirmed":  "Just to be sure — would you like me to reschedule that? Please say yes or no.",
                            "invalid_time":   "I'm sorry, I didn't quite catch a valid time. Could you say it again? For example, \"6:30 in the evening\".",
                            "missing_period": "Could you let me know whether that's in the morning or the evening?",
                            "invalid_date":   "I'm not sure which date you meant. Could you say today, tomorrow, or a specific day?",
                        }
                        clarification = _clarify.get(
                            reason,
                            "I'm sorry, I couldn't confirm the details. Could you say the time again?"
                        )
                        # Keep the session alive so the user can retry
                        return {
                            "action": "reply",
                            "reply": clarification,
                            "intent": "task_followup",
                        }

                    # ---------------------------------------------------
                    # Validation passed — commit in strict order:
                    # 1. build datetime  2. Firestore write  3. delete session
                    # Session is NEVER deleted before the write succeeds.
                    # ---------------------------------------------------
                    confirmed_time = llm_result["time"]
                    confirmed_date = llm_result.get("date") or followup["date"]
                    doc_ref = get_schedule_doc_ref(db, followup["uid"], confirmed_date)

                    try:
                        new_dt = datetime.strptime(
                            f"{confirmed_date} {confirmed_time}",
                            "%Y-%m-%d %H:%M"
                        )
                    except ValueError:
                        new_dt = datetime.utcnow() + timedelta(minutes=10)

                    # Preserve original grace window
                    doc_now = doc_ref.get()
                    grace_minutes = 30
                    if doc_now.exists:
                        tasks_now = doc_now.to_dict().get("tasks", [])
                        task_data = next(
                            (t for t in tasks_now if t.get("id") == followup["task_id"]),
                            None
                        )
                        if task_data:
                            grace_minutes = int(task_data.get("graceMinutes", 30) or 30)

                    valid_until_dt = new_dt + timedelta(minutes=grace_minutes)

                    try:
                        # Step 2 — write to Firestore (may raise)
                        reschedule_task_time(
                            db=db,
                            schedule_doc_ref=doc_ref,
                            uid=followup["uid"],
                            task_id=followup["task_id"],
                            new_time_str=confirmed_time,
                            new_datetime_iso=new_dt.isoformat(),
                            valid_until_iso=valid_until_dt.isoformat(),
                            actor="elder",
                        )
                    except Exception as write_err:
                        # Firestore failed — keep session alive so the user can retry.
                        # Do NOT delete the session here.
                        log_debug("reschedule_firestore_error", {
                            "error": str(write_err),
                            "uid": followup["uid"],
                            "task_id": followup["task_id"],
                            "session_id": session_id,
                        })
                        return {
                            "action": "reply",
                            "reply": (
                                "I'm sorry, I had a little trouble saving that. "
                                "Could you confirm the time once more?"
                            ),
                            "intent": "task_followup",
                        }

                    # Step 3 — Firestore write confirmed, now safe to clean up
                    del pending_task_followups[session_id]

                    # Step 4 — return success
                    return {
                        "action": "reply",
                        "reply": llm_result["reply"],
                        "intent": "task_rescheduled",
                    }

                # Conversation still in progress — return LLM reply, keep session alive
                return {
                    "action": "reply",
                    "reply": llm_result["reply"],
                    "intent": "task_followup",
                }

        # ---------------------------------------------------------
        # 0. Pending confirmation flow for newly extracted tasks
        # ---------------------------------------------------------
        if session_id in pending_confirmations:
            pending = pending_confirmations[session_id]

            if any(x in text for x in ["yes", "yeah", "correct", "yep", "sure", "okay", "ok"]):
                task_name = pending["task_name"]
                time_str = pending["time"]
                target_date = pending.get("date") or (user_now or datetime.now()).strftime("%Y-%m-%d")
                task_uid = pending["uid"]
                frequency = pending.get("frequency", "once")

                try:
                    doc_ref = get_schedule_doc_ref(db, task_uid, target_date)

                    task_type = infer_task_type(task_name)
                    new_task = build_task_occurrence(
                        uid=task_uid,
                        task_name=task_name,
                        task_type=task_type,
                        date_str=target_date,
                        time_str=time_str,
                        risk_level="medium",
                        recurrence_rule=frequency,
                    )

                    doc = doc_ref.get()
                    if not doc.exists:
                        doc_ref.set({
                            "userId": task_uid,
                            "uid": task_uid,
                            "date": target_date,
                            "status": "active",
                            "tasks": [new_task],
                            "created_at": datetime.utcnow().isoformat(),
                        })
                    else:
                        existing = doc.to_dict() or {}
                        tasks = existing.get("tasks", [])
                        tasks.append(new_task)
                        doc_ref.update({
                            "tasks": tasks,
                            "uid": task_uid,
                            "userId": task_uid,
                            "date": target_date,
                        })

                    log_task_event(
                        db=db,
                        uid=task_uid,
                        task_id=new_task["id"],
                        event_type="task_created",
                        actor="system",
                        meta={
                            "task_name": task_name,
                            "scheduledAt": new_task["scheduledAt"],
                            "type": new_task["type"],
                        },
                        confidence="high",
                    )

                    if frequency == "daily":
                        db.collection("common_routine_templates").add({
                            "uid": task_uid,
                            "task_name": task_name,
                            "default_time": time_str,
                            "type": task_type,
                            "created_at": datetime.utcnow().isoformat(),
                            "is_template": True,
                        })

                    del pending_confirmations[session_id]
                    return {
                        "action": "reply",
                        "reply": f"Excellent! I've added '{task_name}' to your schedule. Anything else I can help with?",
                        "intent": "task_saved",
                        "is_confirmation": False,
                    }

                except Exception as save_error:
                    log_debug("save_error", {"error": str(save_error)})
                    del pending_confirmations[session_id]
                    return {
                        "action": "reply",
                        "reply": "I'm sorry, I had a little trouble saving that. Could you try again?",
                        "intent": "error",
                    }

            elif any(x in text for x in ["no", "nope", "wrong", "incorrect", "not correct"]):
                del pending_confirmations[session_id]
                return {
                    "action": "reply",
                    "reply": "No problem at all. I've cleared that. What else is on your mind?",
                    "intent": "task_discarded",
                    "is_confirmation": False,
                }

        # ---------------------------------------------------------
        # 0b. Pending skip confirmation — two-turn confirmation loop
        # ---------------------------------------------------------
        if session_id in pending_skip_confirmations:
            pending = pending_skip_confirmations[session_id]

            if any(x in text for x in ["yes", "yeah", "confirm", "okay", "ok", "do it", "sure", "yep"]):
                doc_ref = get_schedule_doc_ref(db, pending["uid"], pending["date"])
                try:
                    result = handle_task_skip(
                        db=db,
                        schedule_doc_ref=doc_ref,
                        uid=pending["uid"],
                        task_id=pending["task_id"],
                        date=pending["date"],
                        actor=pending["actor"],
                        reason=pending["reason"],
                        confirmed=True,
                    )
                except Exception as skip_err:
                    log_debug("skip_confirm_error", {"error": str(skip_err), "session_id": session_id})
                    del pending_skip_confirmations[session_id]
                    return {
                        "action": "reply",
                        "reply": "I'm sorry, I had trouble skipping that. Please try again.",
                        "intent": "error",
                    }

                del pending_skip_confirmations[session_id]
                notified = result.get("escalation", {}).get("notified", False)
                return {
                    "action": "reply",
                    "reply": (
                        "Okay, I skipped it and informed your caregiver."
                        if notified else
                        "Okay, I skipped it."
                    ),
                    "intent": "task_skipped",
                }

            if any(x in text for x in ["no", "don't", "do not", "cancel", "nope", "never mind"]):
                del pending_skip_confirmations[session_id]
                return {
                    "action": "reply",
                    "reply": "Alright, I will keep the task active.",
                    "intent": "skip_cancelled",
                }

        # ---------------------------------------------------------
        # 1. Fast fallback action detection for very simple phrases
        # ---------------------------------------------------------
        fallback_action = detect_task_action_intent(text)
        if fallback_action:
            today = (user_now or datetime.now()).strftime("%Y-%m-%d")
            doc_ref = get_schedule_doc_ref(db, uid, today)
            applied_action, reply = apply_task_action(db, doc_ref, uid, fallback_action)

            if applied_action == "skip_confirm":
                # Policy requires elder confirmation — store pending and ask
                pending_skip_confirmations[session_id] = {
                    "uid": uid,
                    "date": today,
                    "task_id": fallback_action.get("task_ref", ""),
                    "actor": "elder",
                    "reason": fallback_action.get("reason", "voice_skip"),
                }
                return {
                    "action": "reply",
                    "reply": reply,
                    "intent": "skip_confirmation_required",
                }

            if applied_action:
                return {
                    "action": "reply",
                    "reply": reply,
                    "intent": "task_action",
                    "task_action": applied_action,
                }

        # ---------------------------------------------------------
        # 2. Build current context for LLM
        # ---------------------------------------------------------
        context_summary = await get_context_summary(uid, user_now=user_now)

        # ---------------------------------------------------------
        # 3. Ask LLM for main conversation / task extraction / action extraction
        # ---------------------------------------------------------
        llm_result = await process_voice_with_llm(
            raw_text,
            uid,
            session_id,
            context=context_summary,
            user_now=user_now,
        )

        reply = llm_result["reply"]
        task_preview = llm_result.get("task")
        action_data = llm_result.get("action_data")

        # ---------------------------------------------------------
        # 4. If LLM produced an action, apply it
        # ---------------------------------------------------------
        if action_data:
            today = (user_now or datetime.now()).strftime("%Y-%m-%d")
            doc_ref = get_schedule_doc_ref(db, uid, today)
            applied_action, action_reply = apply_task_action(db, doc_ref, uid, action_data)

            if applied_action == "skip_confirm":
                # Policy requires elder confirmation — store pending and ask
                pending_skip_confirmations[session_id] = {
                    "uid": uid,
                    "date": today,
                    "task_id": action_data.get("task_ref", ""),
                    "actor": "elder",
                    "reason": action_data.get("reason", "voice_skip"),
                }
                return {
                    "action": "reply",
                    "reply": action_reply,
                    "intent": "skip_confirmation_required",
                }

            if applied_action:
                return {
                    "action": "reply",
                    "reply": reply or action_reply,
                    "intent": "task_action",
                    "task_action": applied_action,
                }

            return {
                "action": "reply",
                "reply": action_reply,
                "intent": "task_action",
            }

        # ---------------------------------------------------------
        # 5. If LLM produced a new task, hold it for confirmation
        # ---------------------------------------------------------
        if task_preview:
            task_name = task_preview.get("name", "New Task")
            time_str = task_preview.get("time", "12:00")
            day_phrase = str(task_preview.get("day", "today"))
            target_date = get_target_date(day_phrase, user_now=user_now)

            pending_confirmations[session_id] = {
                "task_name": task_name,
                "time": time_str,
                "date": target_date,
                "uid": uid,
                "frequency": task_preview.get("frequency", "once"),
            }

            return {
                "action": "reply",
                "reply": reply,
                "intent": "task_creation",
                "is_confirmation": True,
                "task": {
                    "name": task_name,
                    "time": time_str,
                    "day_phrase": day_phrase,
                },
            }

        # ---------------------------------------------------------
        # 6. Normal chat reply
        # ---------------------------------------------------------
        return {
            "action": "reply",
            "reply": reply,
            "intent": llm_result["intent"],
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recall_memory")
async def recall_memory(req: VoiceCommandRequest):
    try:
        text = req.text.lower()
        uid = req.uid
        session_id = req.session_id or f"{uid}_recall"
        db = firestore.client()

        user_now = None
        if req.local_time:
            try:
                user_now = datetime.fromisoformat(req.local_time.replace("Z", "+00:00"))
            except Exception:
                pass

        now = user_now or datetime.now()

        t_range = extract_time_range(text)
        is_last = is_last_time_query(text)

        context_parts = []
        dates_to_check = []

        if t_range:
            start_dt, end_dt = t_range
            curr = start_dt.date()
            window_start = (now - timedelta(days=7)).date()
            if curr < window_start:
                curr = window_start

            while curr <= end_dt.date():
                dates_to_check.append(curr.strftime("%Y-%m-%d"))
                curr += timedelta(days=1)
        else:
            for i in range(3):
                dates_to_check.append((now - timedelta(days=i)).strftime("%Y-%m-%d"))

        schedule_context = "Relevant Task Statuses:\n"
        for d_str in dates_to_check:
            doc_ref = get_schedule_doc_ref(db, uid, d_str)
            doc = doc_ref.get()
            if doc.exists:
                tasks = doc.to_dict().get("tasks", [])
                day_label = "Today" if d_str == now.strftime("%Y-%m-%d") else d_str

                for t in tasks:
                    status = t.get("status", "pending")
                    comp_time = ""

                    if t.get("completedAt"):
                        try:
                            ct = datetime.fromisoformat(t["completedAt"]).strftime("%H:%M")
                            comp_time = f" at {ct}"
                        except Exception:
                            pass

                    schedule_context += (
                        f"- {day_label}: {t.get('task_name')} at {t.get('time')} "
                        f"is {status}{comp_time}\n"
                    )

        events_ref = (
            db.collection("task_events")
            .where("uid", "==", uid)
            .order_by("at", direction=firestore.Query.DESCENDING)
            .limit(10)
            .stream()
        )

        event_logs = "Actual Activity Logs:\n"
        for ev in events_ref:
            ev_d = ev.to_dict()
            ev_time = datetime.fromisoformat(ev_d["at"]).strftime("%Y-%m-%d %H:%M")
            event_logs += f"- [{ev_time}] {ev_d.get('type')}: {ev_d.get('meta', {}).get('task_name', 'Activity')}\n"

        context_parts.append(schedule_context)
        context_parts.append(event_logs)

        memories = memory_engine.recall(
            text,
            uid=uid,
            time_range=t_range,
            sort_by_time=is_last,
            top_k=5,
        )
        if memories:
            mem_context = "My Recorded Observations/Notes:\n"
            for m in memories:
                ts = m["timestamp"].strftime("%Y-%m-%d %H:%M") if hasattr(m["timestamp"], "strftime") else str(m["timestamp"])
                mem_context += f"- [{ts}] {m['text']}\n"
            context_parts.append(mem_context)

        full_context = "\n".join(context_parts)

        llm_result = await process_voice_with_llm(
            req.text,
            uid,
            session_id,
            context=full_context,
            system_prompt=RECALL_SYSTEM_PROMPT,
            user_now=now,
        )

        return {
            "action": "reply",
            "reply": llm_result["reply"],
            "intent": "memory_recall",
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/greet")
async def get_greeting(uid: Optional[str] = None):
    import random

    if uid:
        today = datetime.now().strftime("%Y-%m-%d")
        cached = _greeting_cache.get(uid)

        # Return cached greeting if it was generated today
        if cached and cached.get("date") == today:
            return {"reply": cached["reply"]}

        try:
            context = await get_context_summary(uid)
            res = await process_voice_with_llm(
                "Give me a very short, warm, and natural greeting as Alex. Acknowledge the time of day if possible.",
                uid,
                f"{uid}_greet",
                context=context,
            )
            reply = res["reply"]
            # Cache the result for today
            _greeting_cache[uid] = {"date": today, "reply": reply}
            return {"reply": reply}
        except Exception as e:
            from app.services.logger import log_debug
            log_debug("greet_error", {"error": str(e)})

    return {"reply": random.choice(GREETINGS)}


@router.get("/check_profile/{uid}")
async def check_profile(uid: str):
    try:
        db = firestore.client()
        doc = db.collection("elder_profiles").document(uid).get()
        if doc.exists:
            data = doc.to_dict()
            return {"exists": True, **data}
        return {"exists": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create_profile", status_code=201)
async def create_profile(req: ProfileCreateRequest):
    try:
        db = firestore.client()
        uid = req.uid

        profile_data = req.model_dump()
        profile_data["full_name"] = profile_data.pop("name", "User")
        profile_data["is_onboarding_complete"] = True
        profile_data["created_at"] = datetime.utcnow().isoformat()
        profile_data["updated_at"] = datetime.utcnow().isoformat()

        risk_result = predict_elder_risk(profile_data)
        profile_data.update(risk_result)
        profile_data["prediction_updated_at"] = datetime.utcnow().isoformat()

        db.collection("elder_profiles").document(uid).set(profile_data)

        return {
            "message": "Profile created successfully",
            "profile": profile_data,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update_fcm_token")
async def update_fcm_token(req: FCMTokenUpdate):
    try:
        db = firestore.client()
        uid = req.uid
        fcm_token = req.fcm_token

        db.collection("elder_profiles").document(uid).update({
            "fcm_token": fcm_token,
            "updated_at": datetime.utcnow().isoformat(),
        })

        return {"message": "FCM token updated successfully"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/complete")
async def complete_task(req: TaskActionRequest):
    db = firestore.client()
    doc_ref = get_schedule_doc_ref(db, req.uid, req.date)
    mark_completed(db, doc_ref, req.uid, req.task_id, actor=req.actor or "elder")
    return {"status": "ok", "message": "Task marked completed"}


@router.post("/tasks/acknowledge")
async def acknowledge_task(req: TaskActionRequest):
    db = firestore.client()
    doc_ref = get_schedule_doc_ref(db, req.uid, req.date)
    mark_acknowledged(db, doc_ref, req.uid, req.task_id, actor=req.actor or "elder")
    return {"status": "ok", "message": "Task acknowledged"}


@router.post("/tasks/start")
async def start_task(req: TaskActionRequest):
    db = firestore.client()
    doc_ref = get_schedule_doc_ref(db, req.uid, req.date)
    mark_in_progress(db, doc_ref, req.uid, req.task_id, actor=req.actor or "elder")
    return {"status": "ok", "message": "Task in progress"}


@router.post("/tasks/snooze")
async def snooze_task(req: TaskActionRequest):
    db = firestore.client()
    doc_ref = get_schedule_doc_ref(db, req.uid, req.date)
    mark_snoozed(db, doc_ref, req.uid, req.task_id, req.snooze_minutes or 10, actor=req.actor or "elder")
    return {"status": "ok", "message": "Task snoozed"}


@router.post("/tasks/skip")
async def skip_task(req: TaskSkipRequest):
    # Validation
    if not req.reasons:
        raise HTTPException(status_code=400, detail="At least one skip reason is required.")
    
    if (req.skip_decision_by == "caregiver" or req.actor == "caregiver") and not req.caregiver_skip_note:
        raise HTTPException(status_code=400, detail="Caregiver note is required when a caregiver skips a task.")

    db = firestore.client()
    doc_ref = get_schedule_doc_ref(db, req.uid, req.date)

    actor = req.actor or "elder"
    # Safer option: In elder app, lock decisionBy to actor
    skip_decision_by = req.skip_decision_by or actor
    if actor == "elder":
        skip_decision_by = "elder"

    try:
        result = handle_task_skip(
            db=db,
            schedule_doc_ref=doc_ref,
            uid=req.uid,
            task_id=req.task_id,
            date=req.date,
            actor=actor,
            reason=req.reason or (req.reasons[0] if req.reasons else None),
            skip_reasons=req.reasons,
            skip_decision_by=skip_decision_by,
            caregiver_skip_note=req.caregiver_skip_note,
            confirmed=req.confirmed or False,
            notify_caregiver_override=req.notify_caregiver,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    if result["status"] == "confirmation_required":
        return {
            "status": "confirm",
            "message": result["message"],
            "intent": "skip_confirmation_required",
        }

    if result["status"] == "blocked":
        return {
            "status": "blocked",
            "message": result["message"],
            "intent": "task_skip_blocked",
        }

    return {
        "status": "ok",
        "message": "Task skipped",
        "intent": "task_skipped",
        "caregiver_notified": result.get("escalation", {}).get("notified", False),
    }


@router.post("/tasks/review_skip")
async def review_skip(req: ReviewSkipRequest):
    db = firestore.client()
    doc_ref = get_schedule_doc_ref(db, req.uid, req.date)

    try:
        # 1. Update task in schedule
        update_task_in_schedule(
            schedule_doc_ref=doc_ref,
            task_id=req.task_id,
            patch={
                "status": "skipped",
                "skipReviewRequired": False,
                "lastSkipDecisionBy": req.actor,
                "skipReviewedAt": datetime.utcnow().isoformat(),
            }
        )

        # 2. Log review event
        log_task_event(
            db=db,
            uid=req.uid,
            task_id=req.task_id,
            event_type="skip_reviewed",
            by=req.actor,
            meta={
                "date": req.date,
                "review_source": "caregiver_dashboard"
            }
        )

        return {"status": "ok", "message": "Review recorded"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run_reminder_engine")
async def run_reminder_engine():
    """
    Temporary/manual trigger for testing the reminder engine.
    Later, replace this with a scheduler/cron/background worker.
    """
    try:
        results = process_todays_schedules()
        return {
            "status": "ok",
            "processed": results,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
        

@router.post("/tasks/request_later")
async def request_task_later(req: TaskFollowupRequest):
    db = firestore.client()
    doc_ref = get_schedule_doc_ref(db, req.uid, req.date)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Schedule not found")

    tasks = doc.to_dict().get("tasks", [])
    task = next((t for t in tasks if t.get("id") == req.task_id), None)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task_name = task.get("task_name", "this task")
    session_id = req.session_id or f"{req.uid}_default"
    reschedule_session_id = f"{session_id}_reschedule_{req.task_id}"

    # Clear any stale reschedule session for this task
    reset_chat_session(reschedule_session_id)

    # Register the pending followup — LLM will drive the conversation
    pending_task_followups[session_id] = {
        "type": "reschedule_task",
        "uid": req.uid,
        "task_id": req.task_id,
        "date": req.date,
        "task_name": task_name,
        "step": "llm_conversation",
        "version": 1,          # monotonic turn counter — guards against out-of-order responses
    }

    # Use LLM to generate a warm, natural opening question
    user_now = None
    try:
        from datetime import datetime as _dt
        user_now = _dt.now()
    except Exception:
        pass

    llm_opening = await process_reschedule_conversation(
        text="start",  # sentinel — system prompt handles first message
        task_name=task_name,
        session_id=reschedule_session_id,
        user_now=user_now,
    )

    return {
        "action": "reply",
        "reply": llm_opening["reply"],
        "intent": "task_followup",
    }