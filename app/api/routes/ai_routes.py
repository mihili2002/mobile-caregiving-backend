from fastapi import APIRouter, Request, Form, File, UploadFile, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Any
import traceback
import uuid
from datetime import datetime, timedelta
from firebase_admin import firestore

from app.services.extractor import extract_medications
from app.models.schemas import ExtractionResponse, Medication

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Session storage for pending task confirmations
pending_confirmations = {}  # {session_id: {"task_name": "...", "time": "...", "date_offset": 0}}

class VoiceCommandRequest(BaseModel):
    text: str
    uid: str
    session_id: Optional[str] = None

class ProfileCreateRequest(BaseModel):
    uid: str
    name: Optional[str] = None
    age: Optional[int] = None
    long_term_illness: Optional[str] = None
    sleep_well_1to5: Optional[int] = None
    tired_day_1to5: Optional[int] = None
    forget_recent_1to5: Optional[int] = None
    difficulty_remember_tasks_1to5: Optional[int] = None
    forget_take_meds_1to5: Optional[int] = None
    tasks_harder_1to5: Optional[int] = None
    lonely_1to5: Optional[int] = None
    sad_anxious_1to5: Optional[int] = None
    social_talk_1to5: Optional[int] = None
    enjoy_hobbies_1to5: Optional[int] = None
    comfortable_app_1to5: Optional[int] = None
    reminders_helpful_1to5: Optional[int] = None
    reminders_right_time_1to5: Optional[int] = None
    reminders_preference: Optional[str] = None

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
    if x in ["mane", "morning", "am"]:
        return "unknown"
    if x in ["before_meal", "after_meal", "with_meal", "unknown", "bedtime", "night"]:
        return x
    if len(x.split()) == 1 and x.isalpha() and len(x) > 2:
        return x
    return "unknown"

@router.post("/prescriptions/extract", response_model=ExtractionResponse)
async def extract_prescription(elder_id: str = Form(...), file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        filename = file.filename or "prescription"
        content_type = file.content_type or ""

        extracted, method = extract_medications(file_bytes, filename, content_type)
        meds = extracted.get("medications", []) or []

        validated = []
        for m in meds:
             m["timing"] = normalize_timing(str(m.get("timing", "")))
             validated.append(Medication(**m))
        
        return ExtractionResponse(elder_id=elder_id, medications=validated, used_method=method)

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
        from app.services.memory_engine import memory_engine
        from app.services.time_utils import extract_time_range, is_last_time_query, get_schedule_doc_id
        from app.services.classifier import classify_text
        from app.services.response_builder import build_recall_response
        from app.services.logger import log_debug
        from app.services.intent_parser import parse_task_intent
        
        db = firestore.client()
        log_debug("voice_input_received", {"text": text, "uid": uid})

        # --- 0. Check for Pending Confirmation (Yes/No) ---
        if session_id in pending_confirmations:
            pending = pending_confirmations[session_id]
            if any(x in text for x in ["yes", "yeah", "correct", "yep", "sure", "okay", "ok"]):
                task_name = pending["task_name"]
                time_str = pending["time"]
                date_offset = pending["date_offset"]
                task_uid = pending["uid"]
                target_date = (datetime.now() + timedelta(days=date_offset)).strftime("%Y-%m-%d")
                
                try:
                    doc_id = get_schedule_doc_id(task_uid, target_date)
                    doc_ref = db.collection('schedules').document(doc_id)
                    task_id = str(uuid.uuid4())
                    new_task = {
                        "id": task_id,
                        "task_name": task_name,
                        "time": time_str,
                        "type": "common",
                        "completed": False,
                        "completedAt": None,
                        "scheduledAt": datetime.now().isoformat(),
                        "graceMinutes": 30
                    }
                    doc = doc_ref.get()
                    if not doc.exists:
                        doc_ref.set({
                            "userId": task_uid,
                            "date": target_date,
                            "status": "active",
                            "tasks": [new_task],
                            "created_at": datetime.utcnow().isoformat()
                        })
                    else:
                        doc_ref.update({"tasks": firestore.ArrayUnion([new_task])})
                    
                    del pending_confirmations[session_id]
                    day_phrase = "tomorrow" if date_offset == 1 else "today"
                    return {
                        "action": "reply",
                        "reply": f"Great! I've added '{task_name}' to your schedule for {day_phrase} at {time_str}. Anything else?",
                        "intent": "task_saved",
                        "is_confirmation": False,
                        "task": {"name": task_name, "time": time_str, "date_offset": date_offset, "day_phrase": day_phrase, "task_id": task_id}
                    }
                except Exception as save_error:
                    print(f"Error saving confirmed task: {save_error}")
                    del pending_confirmations[session_id]
                    return {"action": "reply", "reply": "I had trouble saving that task. Please try again.", "intent": "error"}
            
            elif any(x in text for x in ["no", "nope", "wrong", "incorrect", "not correct"]):
                del pending_confirmations[session_id]
                return {"action": "reply", "reply": "Okay, I'll discard that. What would you like to add instead?", "intent": "task_discarded", "is_confirmation": False}

        # --- 1. Intent: Recall ---
        if any(x in text for x in ["did i", "have i", "what did i", "when did i", "what have i", "last time"]):
            category = classify_text(text)
            is_last_time = is_last_time_query(text)
            time_range = None if is_last_time else extract_time_range(text)
            
            memories = memory_engine.recall(text, uid=uid, time_range=time_range, distance_threshold=2.0, category_filter=category, sort_by_time=is_last_time)
            
            uncertainty = "low"
            filtered_memories = []
            ask_confirmation = False
            
            if memories:
                top = memories[0]
                top_score = top['score']
                HIGH_CONFIDENCE, CONFIDENCE_THRESHOLD, AMBIGUITY_MARGIN = 0.9, 1.2, 0.1
                if is_last_time: CONFIDENCE_THRESHOLD = 1.6 
                
                if top_score > CONFIDENCE_THRESHOLD:
                    uncertainty = "low"
                else:
                    filtered_memories = [top]
                    if len(memories) > 1 and not is_last_time:
                        second = memories[1]
                        if abs(second['score'] - top_score) < AMBIGUITY_MARGIN:
                             uncertainty = "ambiguous"
                             filtered_memories = [top, second]
                        elif top_score < HIGH_CONFIDENCE: uncertainty = "high"
                        else: uncertainty = "medium"
                    else:
                        uncertainty = "high" if top_score < HIGH_CONFIDENCE else "medium"

                if category == "medication" and uncertainty in ["high", "medium"]:
                    ask_confirmation = True

            reply = build_recall_response(filtered_memories, time_range, uncertainty, ask_confirmation)
            return {"action": "reply", "reply": reply, "intent": "recall"}

        # --- 2. Intent: Completion ---
        if any(x in text for x in ["i have", "i did", "i finished", "completed", "done with", "took my"]):
             memory_engine.store_memory(text, {"uid": uid, "type": "activity_log"})
             return {"action": "reply", "reply": "Okay, I've saved that to your memory.", "intent": "activity_log"}

        # --- 3. Task Creation ---
        df_triggers = ["remind", "add", "schedule", "task", "plan", "tomorrow", "today", " am", " pm", "at ", ":", "drink", "take", "eat", "buy", "go to", "call"]
        import re
        if bool(re.search(r'\b\d{3,4}\b', text)) or any(x in text for x in df_triggers):
            parsed = parse_task_intent(text)
            if parsed.get("is_termination"):
                return {"action": "close", "reply": "Great, your plan is all set. Have a wonderful day!", "intent": "termination"}
            
            if parsed.get("is_task_request"):
                task_name, time_str, date_offset = parsed.get("task_name"), parsed.get("time", "12:00"), parsed.get("date_offset", 0)
                
                if session_id in pending_confirmations:
                    old = pending_confirmations[session_id]
                    try:
                        old_date = (datetime.now() + timedelta(days=old["date_offset"])).strftime("%Y-%m-%d")
                        doc_id = get_schedule_doc_id(old["uid"], old_date)
                        db.collection('schedules').document(doc_id).set({
                            "userId": old["uid"], "date": old_date, "status": "active", "created_at": datetime.utcnow().isoformat(),
                            "tasks": firestore.ArrayUnion([{
                                "id": str(uuid.uuid4()), "task_name": old["task_name"], "time": old["time"], "type": "common",
                                "completed": False, "completedAt": None, "scheduledAt": datetime.now().isoformat(), "graceMinutes": 30
                            }])
                        }, merge=True)
                    except Exception as e: print(f"[AUTO-CONFIRM] Error: {e}")
                
                pending_confirmations[session_id] = {"task_name": task_name, "time": time_str, "date_offset": date_offset, "uid": uid}
                day_phrase = "tomorrow" if date_offset == 1 else "today"
                return {
                    "action": "reply", "reply": f"I heard you say: '{req.text}'. I heard '{task_name}' at {time_str} for {day_phrase}. Is that correct? Say yes or no.",
                    "intent": "task_creation", "is_confirmation": True, "task": {"name": task_name, "time": time_str, "date_offset": date_offset, "day_phrase": day_phrase}
                }

        # --- 4. Fallback: Close ---
        if any(x in text for x in ["nothing more", "no more", "that is all", "that's all", "all done", "nothing else", "no thanks"]):
             return {"action": "close", "reply": "Great, your plan is all set. Have a wonderful day!"}

        # --- 5. Fallback: Schedule info ---
        from app.services.time_utils import get_schedule_doc_id
        doc_id = get_schedule_doc_id(uid, datetime.now().strftime("%Y-%m-%d"))
        doc = db.collection('schedules').document(doc_id).get()
        if doc.exists and ("schedule" in text or "tasks" in text):
             count = len([t for t in doc.to_dict().get('tasks', []) if not t.get('completed')])
             return {"action": "reply", "reply": f"You have {count} tasks remaining for today. Is there anything else you'd like to add or ask?"}
        
        return {"action": "reply", "reply": "I'm listening. You can tell me what you did, ask me about past activities, or add a task to your schedule. Is there anything else for today?"}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/check_profile/{uid}")
async def check_profile(uid: str):
    try:
        db = firestore.client()
        doc = db.collection('elder_profiles').document(uid).get()
        if doc.exists:
            data = doc.to_dict()
            return {
                "exists": True,
                **data
            }
        return {"exists": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create_profile", status_code=201)
async def create_profile(req: ProfileCreateRequest):
    try:
        db = firestore.client()
        uid = req.uid
        
        # Merge validated fields from Pydantic model
        profile_data = req.model_dump(exclude_unset=True)
        
        # Ensure default behavior metrics (Cold Start)
        defaults = {
            "missed_meds_per_week": 0,
            "missed_tasks_per_week": 0,
            "avg_task_delay_min": 0,
            "snoozes_per_day": 0,
            "is_onboarding_complete": True,  # Mark as complete upon creation
            "created_at": datetime.utcnow().isoformat()
        }
        for k, v in defaults.items():
            if k not in profile_data:
                profile_data[k] = v

        # --- Run Prediction ---
        from app.services.ml_inference import predict_elder_risk
        risk_result = predict_elder_risk(profile_data)
        risk_result['prediction_updated_at'] = datetime.utcnow().isoformat()
        profile_data.update(risk_result)

        db.collection('elder_profiles').document(uid).set(profile_data, merge=True)
        return {"message": "Profile created", "profile": profile_data}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
