from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form, Request
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
import traceback
from datetime import datetime, timedelta
from firebase_admin import firestore
import re

from app.models.schemas import ExtractionResponse, Medication
from app.services.openai_service import process_voice_with_llm, RECALL_SYSTEM_PROMPT
from app.services.memory_engine import memory_engine
from app.services.time_utils import extract_time_range, is_last_time_query, combine_date_time
from app.services.extractor import extract_medications
from app.services.voice_processing_service import voice_processing_service # Kept for process_audio_command
from app.services.strategy_service import get_reminder_strategy # Kept for predict_reminder_strategy and predict_task_risk
from app.services.ml_inferences import predict_elder_risk # Kept for predict_elder_risk and create_profile
from app.core.firebase import get_db # Kept for predict_reminder_strategy

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
            # Return a default strategy if profile doesn't exist yet
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
        
        # 1. Get Base Risk from ML Model
        risk_data = predict_elder_risk(profile)
        
        # 2. Get Strategy (Retries/Escalation)
        strategy_data = get_reminder_strategy(profile)
        strategy = strategy_data.get("strategy", {})

        # 3. Map to RoutineAIInsights expected by Frontend
        # Frontend check: lib/models/routine_models.dart -> RoutineAIInsights.fromJson
        insights = {
            "ai_completion_prob": 1.0 - risk_data.get("prediction_probability", 0.5), # Probability of DOING it
            "ai_expected_delay": strategy.get("expected_delay_min", 0),
            "ai_predicted_retries": strategy.get("auto_retries_count", 1),
            "ai_predicted_snoozes": strategy.get("max_snoozes_allowed", 3),
            "ai_needs_escalation": strategy.get("caregiver_escalation_enabled", False)
        }

        return {"status": "success", "predictions": insights}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class VoiceCommandRequest(BaseModel):
    text: str
    uid: str
    session_id: Optional[str] = None
    local_time: Optional[str] = None # NEW: ISO8601 string from phone

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

# In-memory storage for pending confirmations (simplified for demo)
# In production, use Redis or Firestore
pending_confirmations = {}  # {session_id: {"task_name": "...", "time": "...", "date_offset": 0}}

GREETINGS = [
    "Hi there! I'm Alex, your routine coach. How can I help you today?",
    "Hello! Alex here. Ready to plan your day?",
    "Good day! I'm Alex. What's on your mind?",
    "Hi! It's Alex. I'm here to help with your schedule or any memories.",
    "Hey! Alex is ready! How can I support you right now?"
]

def get_target_date(day_str: str, user_now: Optional[datetime] = None) -> str:
    """Calculates the YYYY-MM-DD string for a given day description."""
    day_str = day_str.lower()
    now = user_now or datetime.now()
    if "today" in day_str:
        return now.strftime("%Y-%m-%d")
    if "tomorrow" in day_str:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Check for days of week
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, d in enumerate(days):
        if d in day_str:
            target_weekday = i
            current_weekday = now.weekday()
            days_ahead = target_weekday - current_weekday
            if days_ahead < 0: # Already passed this week
                days_ahead += 7
            elif days_ahead == 0 and "next" in day_str:
                days_ahead = 7
            
            return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    return now.strftime("%Y-%m-%d")

async def get_context_summary(uid: str, user_now: Optional[datetime] = None) -> str:
    """Fetches a summary of today's schedule to provide context for the LLM."""
    try:
        from app.services.time_utils import get_schedule_doc_id
        db = firestore.client()
        now = user_now or datetime.now()
        today = now.strftime("%Y-%m-%d")
        doc_id = get_schedule_doc_id(uid, today)
        doc = db.collection('schedules').document(doc_id).get()
        
        if not doc.exists:
            return "No tasks scheduled for today yet."
        
        data = doc.to_dict()
        tasks = data.get("tasks", [])
        if not tasks:
            return "The schedule for today is empty."
        
        summary = "Today's Schedule:\n"
        for t in tasks:
            status = "Completed" if t.get("completed") else "Pending"
            summary += f"- {t.get('task_name')} at {t.get('time')} ({status})\n"
        return summary
    except Exception as e:
        return f"Error fetching context: {str(e)}"

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
    
    # Check for direct matches with allowed literals
    allowed = {"before_meal", "after_meal", "with_meal", "bedtime", "morning", "afternoon", "evening", "as_needed", "unknown"}
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
             
             # Post-extraction normalization for frequency if LLM missed it but got the text
             if not m.get("frequency_per_day") and m.get("frequency_text"):
                 f_text = str(m.get("frequency_text", "")).lower()
                 if "od" in f_text: m["frequency_per_day"] = 1
                 elif "bd" in f_text: m["frequency_per_day"] = 2
                 elif "tds" in f_text or "tid" in f_text: m["frequency_per_day"] = 3
                 elif "qid" in f_text: m["frequency_per_day"] = 4
             
             # Duration parsing
             if not m.get("duration_days") and m.get("duration_text"):
                 m["duration_days"] = parse_duration_days(m.get("duration_text"))
             
             # Dosage compatibility for UI
             s = m.get("strength")
             m["dosage"] = s or "unknown"
             
             # Clean drug name (restored/refined)
             m["drug_name"] = clean_drug_prefix(m.get("drug_name", ""))

             # Date calculation
             if not m.get("from_date"):
                 m["from_date"] = datetime.now().strftime("%Y-%m-%d")
             
             if m.get("duration_days") and m.get("from_date"):
                 try:
                     start_dt = datetime.strptime(m["from_date"], "%Y-%m-%d")
                     end_dt = start_dt + timedelta(days=m["duration_days"])
                     m["to_date"] = end_dt.strftime("%Y-%m-%d")
                 except:
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
async def process_audio_command(uid: str = Form(...), session_id: Optional[str] = Form(None), file: UploadFile = File(...)):
    """
    Handles audio files, transcribes them using Whisper, and then
    processes the command exactly like the text-based endpoint.
    """
    try:
        # 1. Read Audio File
        audio_bytes = await file.read()
        
        # 2. Transcribe using VoiceProcessingService (includes noise reduction)
        text = voice_processing_service.transcribe(audio_bytes)
        
        if text.startswith("ERROR:"):
             return {"action": "reply", "reply": "I'm sorry, I couldn't understand the audio. Please try again.", "error": text}

        # 3. Reuse text-based processing logic
        voice_command_req = VoiceCommandRequest(text=text, uid=uid, session_id=session_id)
        result = await process_voice_command(voice_command_req)
        
        # Add the transcribed text to the response so the UI can show it
        if isinstance(result, dict):
            result["transcribed_text"] = text
        
        return result

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/process_voice_command")
async def process_voice_command(req: VoiceCommandRequest):
    try:
        text = req.text.lower()
        uid = req.uid
        session_id = req.session_id or f"{uid}_default"

        # --- Imports (Late to avoid cycles) ---
        from app.services.time_utils import get_schedule_doc_id
        from app.services.logger import log_debug
        
        db = firestore.client()
        log_debug("voice_input_received", {"text": text, "uid": uid})

        # Parse user local time
        user_now = None
        if req.local_time:
            try:
                user_now = datetime.fromisoformat(req.local_time.replace('Z', '+00:00'))
            except: pass

        # --- 0. Check for Pending Confirmation (Yes/No) ---
        if session_id in pending_confirmations:
            pending = pending_confirmations[session_id]
            if any(x in text for x in ["yes", "yeah", "correct", "yep", "sure", "okay", "ok"]):
                task_name = pending["task_name"]
                time_str = pending["time"]
                target_date = pending.get("date") or (user_now or datetime.now()).strftime("%Y-%m-%d")
                task_uid = pending["uid"]
                frequency = pending.get("frequency", "once")
                
                try:
                    doc_id = get_schedule_doc_id(task_uid, target_date)
                    doc_ref = db.collection('schedules').document(doc_id)
                    
                    # 1. Main Task
                    task_id = str(uuid.uuid4())
                    scheduled_at = combine_date_time(target_date, time_str)
                    
                    new_task = {
                        "id": task_id, "task_name": task_name, "time": time_str, "type": "common",
                        "completed": False, "completedAt": None, "scheduledAt": scheduled_at, "graceMinutes": 30
                    }
                    
                    doc = doc_ref.get()
                    if not doc.exists:
                        doc_ref.set({
                            "userId": task_uid, 
                            "uid": task_uid,
                            "date": target_date, 
                            "status": "active", 
                            "tasks": [new_task], 
                            "created_at": datetime.utcnow().isoformat()
                        })
                    else:
                        # Ensure fields exist for the listener
                        doc_ref.update({
                            "tasks": firestore.ArrayUnion([new_task]),
                            "uid": task_uid,
                            "userId": task_uid,
                            "date": target_date
                        })
                    
                    # 2. Daily Template
                    if frequency == "daily":
                        db.collection("common_routine_templates").add({
                            "uid": task_uid, "task_name": task_name, "default_time": time_str,
                            "type": "common", "created_at": datetime.utcnow().isoformat(), "is_template": True
                        })

                    del pending_confirmations[session_id]
                    return {
                        "action": "reply",
                        "reply": f"Excellent! I've added '{task_name}' to your schedule. Anything else I can help with?",
                        "intent": "task_saved", "is_confirmation": False
                    }
                except Exception as save_error:
                    log_debug("save_error", {"error": str(save_error)})
                    del pending_confirmations[session_id]
                    return {"action": "reply", "reply": "I'm sorry, I had a little trouble saving that. Could you try again?", "intent": "error"}
            
            elif any(x in text for x in ["no", "nope", "wrong", "incorrect", "not correct"]):
                del pending_confirmations[session_id]
                return {"action": "reply", "reply": "No problem at all. I've cleared that. What else is on your mind?", "intent": "task_discarded", "is_confirmation": False}

        # --- 1. Get Context ---
        context_summary = await get_context_summary(uid, user_now=user_now)

        # --- 2. Use OpenAI for the main conversation ---
        llm_result = await process_voice_with_llm(req.text, uid, session_id, context=context_summary, user_now=user_now)
        reply = llm_result["reply"]
        task_preview = llm_result.get("task")
        
        if task_preview:
            # Prepare for confirmation
            task_name = task_preview.get("name", "New Task")
            time_str = task_preview.get("time", "12:00")
            day_phrase = str(task_preview.get("day", "today"))
            target_date = get_target_date(day_phrase, user_now=user_now)
            
            pending_confirmations[session_id] = {
                "task_name": task_name,
                "time": time_str,
                "date": target_date,
                "uid": uid,
                "frequency": task_preview.get("frequency", "once")
            }
            
            return {
                "action": "reply", "reply": reply, "intent": "task_creation", "is_confirmation": True,
                "task": {"name": task_name, "time": time_str, "day_phrase": day_phrase}
            }
        
        # Simple chat reply
        return {"action": "reply", "reply": reply, "intent": llm_result["intent"]}

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

        # Parse user local time
        user_now = None
        if req.local_time:
            try:
                user_now = datetime.fromisoformat(req.local_time.replace('Z', '+00:00'))
            except: pass
        
        now = user_now or datetime.now()

        # 1. Identify Time Range
        t_range = extract_time_range(text)
        is_last = is_last_time_query(text)
        
        context_parts = []
        
        # 2. Fetch Schedule Statuses & Events (Last 7 Days)
        dates_to_check = []
        if t_range:
             start_dt, end_dt = t_range
             curr = start_dt.date()
             window_start = (now - timedelta(days=7)).date()
             if curr < window_start: curr = window_start
             
             while curr <= end_dt.date():
                 dates_to_check.append(curr.strftime("%Y-%m-%d"))
                 curr += timedelta(days=1)
        else:
             for i in range(3):
                 dates_to_check.append((now - timedelta(days=i)).strftime("%Y-%m-%d"))

        schedule_context = "Relevant Task Statuses:\n"
        from app.services.time_utils import get_schedule_doc_id
        for d_str in dates_to_check:
            doc_id = get_schedule_doc_id(uid, d_str)
            doc = db.collection('schedules').document(doc_id).get()
            if doc.exists:
                tasks = doc.to_dict().get("tasks", [])
                day_label = "Today" if d_str == now.strftime("%Y-%m-%d") else d_str
                for t in tasks:
                    status = "Completed" if t.get("completed") else "Pending"
                    comp_time = ""
                    if t.get("completedAt"):
                         try:
                             ct = datetime.fromisoformat(t['completedAt']).strftime("%H:%M")
                             comp_time = f" at {ct}"
                         except: pass
                    schedule_context += f"- {day_label}: {t.get('task_name')} at {t.get('time')} is {status}{comp_time}\n"
        
        # 2.5 Fetch Recent Events
        events_ref = db.collection('task_events').where("uid", "==", uid)\
                       .order_by("at", direction=firestore.Query.DESCENDING).limit(10).stream()
        event_logs = "Actual Activity Logs:\n"
        for ev in events_ref:
            ev_d = ev.to_dict()
            ev_time = datetime.fromisoformat(ev_d['at']).strftime("%Y-%m-%d %H:%M")
            event_logs += f"- [{ev_time}] {ev_d.get('type')}: {ev_d.get('meta', {}).get('task_name', 'Activity')}\n"
        
        context_parts.append(schedule_context)
        context_parts.append(event_logs)

        # 3. Fetch Semantic Memories
        memories = memory_engine.recall(text, uid=uid, time_range=t_range, sort_by_time=is_last, top_k=5)
        if memories:
            mem_context = "My Recorded Observations/Notes:\n"
            for m in memories:
                ts = m['timestamp'].strftime("%Y-%m-%d %H:%M") if hasattr(m['timestamp'], 'strftime') else str(m['timestamp'])
                mem_context += f"- [{ts}] {m['text']}\n"
            context_parts.append(mem_context)
        
        full_context = "\n".join(context_parts)

        # 4. Use LLM with RECALL prompt
        llm_result = await process_voice_with_llm(
            req.text, uid, session_id, context=full_context, system_prompt=RECALL_SYSTEM_PROMPT, user_now=now
        )
        
        return {"action": "reply", "reply": llm_result["reply"], "intent": "memory_recall"}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/greet")
async def get_greeting(uid: Optional[str] = None):
    if uid:
        try:
            context = await get_context_summary(uid)
            res = await process_voice_with_llm("Give me a very short, warm, and natural greeting as Alex. Acknowledge the time of day if possible.", uid, f"{uid}_greet", context=context)
            return {"reply": res["reply"]}
        except Exception as e:
            from app.services.logger import log_debug
            log_debug("greet_error", {"error": str(e)})
    
    import random
    return {"reply": random.choice(GREETINGS)}

@router.get("/check_profile/{uid}")
async def check_profile(uid: str):
    try:
        db = firestore.client()
        doc = db.collection('elder_profiles').document(uid).get()
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
        profile_data['full_name'] = profile_data.pop('name', 'User')
        profile_data['is_onboarding_complete'] = True
        profile_data['created_at'] = datetime.utcnow().isoformat()
        profile_data['updated_at'] = datetime.utcnow().isoformat()
        
        risk_result = predict_elder_risk(profile_data)
        profile_data.update(risk_result)
        profile_data['prediction_updated_at'] = datetime.utcnow().isoformat()
        
        db.collection('elder_profiles').document(uid).set(profile_data)
        
        return {
            "message": "Profile created successfully",
            "profile": profile_data
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
        
        db.collection('elder_profiles').document(uid).update({
            "fcm_token": fcm_token,
            "updated_at": datetime.utcnow().isoformat()
        })
        
        return {"message": "FCM token updated successfully"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))