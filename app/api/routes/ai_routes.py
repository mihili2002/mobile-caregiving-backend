from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
import traceback
from datetime import datetime, timedelta
from firebase_admin import firestore

from app.models.schemas import ExtractionResponse, Medication
from app.services.openai_service import process_voice_with_llm

router = APIRouter(prefix="/api/ai", tags=["ai"])

class VoiceCommandRequest(BaseModel):
    text: str
    uid: str
    session_id: Optional[str] = None

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

def get_target_date(day_str: str) -> str:
    """Calculates the YYYY-MM-DD string for a given day description."""
    day_str = day_str.lower()
    now = datetime.now()
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

async def get_context_summary(uid: str) -> str:
    """Fetches a summary of today's schedule to provide context for the LLM."""
    try:
        from app.services.time_utils import get_schedule_doc_id
        db = firestore.client()
        today = datetime.now().strftime("%Y-%m-%d")
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

        # --- 0. Check for Pending Confirmation (Yes/No) ---
        if session_id in pending_confirmations:
            pending = pending_confirmations[session_id]
            if any(x in text for x in ["yes", "yeah", "correct", "yep", "sure", "okay", "ok"]):
                task_name = pending["task_name"]
                time_str = pending["time"]
                target_date = pending.get("date", datetime.now().strftime("%Y-%m-%d"))
                task_uid = pending["uid"]
                frequency = pending.get("frequency", "once")
                reminder_offset = pending.get("reminder_offset_mins", 0)
                
                try:
                    doc_id = get_schedule_doc_id(task_uid, target_date)
                    doc_ref = db.collection('schedules').document(doc_id)
                    
                    # 1. Main Task
                    task_id = str(uuid.uuid4())
                    new_task = {
                        "id": task_id, "task_name": task_name, "time": time_str, "type": "common",
                        "completed": False, "completedAt": None, "scheduledAt": datetime.now().isoformat(), "graceMinutes": 30
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
                        doc_ref.update({"tasks": firestore.ArrayUnion([new_task])})
                    
                    # 2. Daily Template
                    if frequency == "daily":
                        db.collection("common_routine_templates").add({
                            "uid": task_uid, "task_name": task_name, "default_time": time_str,
                            "type": "common", "created_at": datetime.utcnow().isoformat(), "is_template": True
                        })

                    # 3. Proactive Reminder Task
                    if reminder_offset > 0:
                        try:
                            # Calculate reminder time
                            h, m = map(int, time_str.split(':'))
                            rem_dt = datetime.combine(datetime.now().date(), time(h, m)) - timedelta(minutes=reminder_offset)
                            rem_time = rem_dt.strftime("%H:%M")
                            
                            rem_task_id = str(uuid.uuid4())
                            rem_task = {
                                "id": rem_task_id, "task_name": f"Reminder: {task_name}", "time": rem_time, "type": "common",
                                "completed": False, "completedAt": None, "scheduledAt": datetime.now().isoformat(), "graceMinutes": 5
                            }
                            doc_ref.update({"tasks": firestore.ArrayUnion([rem_task])})
                        except: pass # Non-critical if reminder fails

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
        context_summary = await get_context_summary(uid)

        # --- 2. Use OpenAI for the main conversation ---
        llm_result = await process_voice_with_llm(req.text, uid, session_id, context=context_summary)
        reply = llm_result["reply"]
        task_preview = llm_result.get("task")
        
        if task_preview:
            # Prepare for confirmation
            task_name = task_preview.get("name", "New Task")
            time_str = task_preview.get("time", "12:00")
            day_str = str(task_preview.get("day", "today"))
            target_date = get_target_date(day_str)
            
            pending_confirmations[session_id] = {
                "task_name": task_name,
                "time": time_str,
                "date": target_date,
                "uid": uid,
                "frequency": task_preview.get("frequency", "once"),
                "reminder_offset_mins": task_preview.get("reminder_offset_mins", 0)
            }
            
            return {
                "action": "reply", "reply": reply, "intent": "task_creation", "is_confirmation": True,
                "task": {"name": task_name, "time": time_str, "day_phrase": day_str}
            }
        
        # Simple chat reply
        return {"action": "reply", "reply": reply, "intent": llm_result["intent"]}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/greet")
async def get_greeting(uid: Optional[str] = None):
    # If we have a uid, we can make the greeting context-aware!
    if uid:
        try:
            context = await get_context_summary(uid)
            # Use LLM for a truly natural greeting
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
        from app.services.ml_inferences import predict_elder_risk
        db = firestore.client()
        uid = req.uid
        
        # 1. Convert request to dict and add metadata
        profile_data = req.dict()
        profile_data['full_name'] = profile_data.pop('name', 'User')
        profile_data['is_onboarding_complete'] = True
        profile_data['created_at'] = datetime.utcnow().isoformat()
        profile_data['updated_at'] = datetime.utcnow().isoformat()
        
        # 2. Run Risk Assessment immediately
        risk_result = predict_elder_risk(profile_data)
        profile_data.update(risk_result)
        profile_data['prediction_updated_at'] = datetime.utcnow().isoformat()
        
        # 3. Save to Firestore
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
