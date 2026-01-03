from flask import Blueprint, request, jsonify
import traceback

from app.services.extractor import extract_medications
from app.models.schemas import ExtractionResponse, Medication
from datetime import datetime, timedelta
import uuid

ai_bp = Blueprint("ai_bp", __name__)

# Session storage for pending task confirmations
pending_confirmations = {}  # {session_id: {"task_name": "...", "time": "...", "date_offset": 0}}


def normalize_timing(t: str) -> str:
    if not t:
        return "unknown"
    x = t.strip().lower()

    # common prescription Latin / abbreviations
    if x in ["ac", "a.c", "before food", "before meal"]:
        return "before_meal"
    if x in ["pc", "p.c", "after food", "after meal"]:
        return "after_meal"
    if x in ["with food", "with meal"]:
        return "with_meal"

    # common OCR/LLM outputs
    if x in ["mane", "morning", "am"]:
        # morning doesn't necessarily mean before/after meal → safest:
        return "unknown"

    # already valid or common
    if x in ["before_meal", "after_meal", "with_meal", "unknown", "bedtime", "night"]:
        return x
    
    # If it's a single word and reasonably likely to be a timing, keep it
    if len(x.split()) == 1 and x.isalpha() and len(x) > 2:
        return x

    return "unknown"

@ai_bp.route("/prescriptions/extract", methods=["POST"])
def extract_prescription():
    try:
        elder_id = request.form.get("elder_id")
        file = request.files.get("file")

        if not elder_id or not file:
            return jsonify({"error": "elder_id and file are required"}), 400

        file_bytes = file.read()
        filename = file.filename or "prescription"
        content_type = file.content_type or ""

        extracted, method = extract_medications(file_bytes, filename, content_type)
        meds = extracted.get("medications", []) or []

        validated = []
        for m in meds:
             m["timing"] = normalize_timing(str(m.get("timing", "")))
             validated.append(Medication(**m).model_dump())
        resp = ExtractionResponse(elder_id=elder_id, medications=validated, used_method=method).model_dump()
        return jsonify(resp), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@ai_bp.route("/process_voice_command", methods=["POST"])
def process_voice_command():
    try:
        data = request.json
        text = data.get("text", "").lower()
        uid = data.get("uid")
        session_id = data.get("session_id") or f"{uid}_default"

        # --- Imports ---
        from app.services.memory_engine import memory_engine
        from app.services.time_utils import extract_time_range, is_last_time_query, get_schedule_doc_id
        from app.services.classifier import classify_text
        from app.services.response_builder import build_recall_response
        from app.services.logger import log_debug
        from app.services.intent_parser import parse_task_intent # New Module
        from firebase_admin import firestore
        
        db = firestore.client()
        print(f"DEBUG: timedelta accessible? {timedelta}")
        log_debug("voice_input_received", {"text": text, "uid": uid})

        # --- 0. Check for Pending Confirmation (Yes/No) ---
        if session_id in pending_confirmations:
            pending = pending_confirmations[session_id]
            
            # User confirms (Yes)
            if any(x in text for x in ["yes", "yeah", "correct", "yep", "sure", "okay", "ok"]):
                # Extract pending task data
                task_name = pending["task_name"]
                time_str = pending["time"]
                date_offset = pending["date_offset"]
                task_uid = pending["uid"]
                
                # Calculate target date
                target_date = (datetime.now() + timedelta(days=date_offset)).strftime("%Y-%m-%d")
                
                try:
                    # Save task to Firestore
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
                        from firebase_admin import firestore as fs
                        doc_ref.update({
                            "tasks": fs.ArrayUnion([new_task])
                        })
                    
                    # Clear pending confirmation
                    del pending_confirmations[session_id]
                    
                    # Success message
                    day_phrase = "tomorrow" if date_offset == 1 else "today"
                    reply = f"Great! I've added '{task_name}' to your schedule for {day_phrase} at {time_str}. Anything else?"
                    
                    return jsonify({
                        "action": "reply",
                        "reply": reply,
                        "intent": "task_saved",
                        "is_confirmation": False,
                        "task": {
                            "name": task_name,
                            "time": time_str,
                            "date_offset": date_offset,
                            "day_phrase": day_phrase,
                            "task_id": task_id
                        }
                    }), 200
                    
                except Exception as save_error:
                    print(f"Error saving confirmed task: {save_error}")
                    del pending_confirmations[session_id]  # Clear even on error
                    return jsonify({
                        "action": "reply",
                        "reply": "I had trouble saving that task. Please try again.",
                        "intent": "error"
                    }), 200
            
            # User rejects (No)
            elif any(x in text for x in ["no", "nope", "wrong", "incorrect", "not correct"]):
                del pending_confirmations[session_id]
                return jsonify({
                    "action": "reply",
                    "reply": "Okay, I'll discard that. What would you like to add instead?",
                    "intent": "task_discarded",
                    "is_confirmation": False
                }), 200

        # --- 1. Intent: Recall ("Did I...?", "When did I...?") ---
        # Moving Recall FIRST to capture questions even if they contain keywords like "add" or "plan"
        if any(x in text for x in ["did i", "have i", "what did i", "when did i", "what have i", "last time"]):
            
            # A. Analysis
            category = classify_text(text)
            is_last_time = is_last_time_query(text)
            
            time_range = None
            if not is_last_time:
                time_range = extract_time_range(text)
            
            log_debug("recall_analysis", {
                "category": category, 
                "is_last_time": is_last_time, 
                "time_range": time_range
            })
            
            # B. Retrieval
            memories = memory_engine.recall(
                text, 
                uid=uid, 
                time_range=time_range, 
                distance_threshold=2.0, # Loose for candidates
                category_filter=category,
                sort_by_time=is_last_time
            )
            
            log_debug("recall_results", {
                "count": len(memories),
                "top_score": memories[0]['score'] if memories else None
            })
            
            # C. Uncertainty & Confirmation Logic
            uncertainty = "low"
            filtered_memories = []
            ask_confirmation = False
            
            if memories:
                top = memories[0]
                top_score = top['score']
                
                # Thresholds
                HIGH_CONFIDENCE = 0.9
                CONFIDENCE_THRESHOLD = 1.2
                AMBIGUITY_MARGIN = 0.1
                
                if is_last_time:
                     CONFIDENCE_THRESHOLD = 1.6 
                
                if top_score > CONFIDENCE_THRESHOLD:
                    uncertainty = "low"
                else:
                    filtered_memories = [top]
                    
                    if len(memories) > 1 and not is_last_time:
                        second = memories[1]
                        if abs(second['score'] - top_score) < AMBIGUITY_MARGIN:
                             uncertainty = "ambiguous"
                             filtered_memories = [top, second]
                        elif top_score < HIGH_CONFIDENCE:
                             uncertainty = "high"
                        else:
                             uncertainty = "medium"
                    else:
                        if top_score < HIGH_CONFIDENCE:
                            uncertainty = "high"
                        else:
                            uncertainty = "medium"

                # Check Confirmation
                if category == "medication" and uncertainty in ["high", "medium"]:
                    ask_confirmation = True

            # D. Build Response
            reply = build_recall_response(filtered_memories, time_range, uncertainty, ask_confirmation)
            log_debug("recall_response", {"reply": reply, "uncertainty": uncertainty})
            
            return jsonify({
                "action": "reply",
                "reply": reply,
                "intent": "recall"
            }), 200

        # --- 2. Intent: Completion ("I did X") ---
        # Heuristic: starts with completion phrases
        if any(x in text for x in ["i have", "i did", "i finished", "completed", "done with", "took my"]):
             # Store this as a memory
             memory_engine.store_memory(text, {"uid": uid, "type": "activity_log"})
             
             reply = "Okay, I've saved that to your memory."
             log_debug("intent_completion", {"reply": reply})
             
             return jsonify({
                 "action": "reply",
                 "reply": reply,
                 "intent": "activity_log"
             }), 200

        # --- 3. Task Creation (Local Intent Parsing) ---
        # Use local intent parser instead of Dialogflow
        from app.services.intent_parser import parse_task_intent
        
        # Triggers for task-related requests
        df_triggers = ["remind", "add", "schedule", "task", "plan", "tomorrow", "today", " am", " pm", "at ", ":", "drink", "take", "eat", "buy", "go to", "call"]
        
        # Also trigger if it looks like there's a time number (e.g. "245", "1030")
        import re
        has_time_number = bool(re.search(r'\b\d{3,4}\b', text))
        
        if has_time_number or any(x in text for x in df_triggers):
            parsed = parse_task_intent(text)
            
            # Check for termination
            if parsed.get("is_termination"):
                return jsonify({
                    "action": "close",
                    "reply": "Great, your plan is all set. Have a wonderful day!",
                    "intent": "termination"
                }), 200
            
            # Check if it's a task request
            if parsed.get("is_task_request"):
                task_name = parsed.get("task_name")
                time_str = parsed.get("time", "12:00")
                date_offset = parsed.get("date_offset", 0)
                
                # --- AUTO-CONFIRM PREVIOUS PENDING TASK (if exists) ---
                if session_id in pending_confirmations:
                    old_pending = pending_confirmations[session_id]
                    print(f"[AUTO-CONFIRM] Saving previous pending task: {old_pending['task_name']}")
                    
                    # Save the old pending task automatically
                    old_task_name = old_pending["task_name"]
                    old_time_str = old_pending["time"]
                    old_date_offset = old_pending["date_offset"]
                    old_uid = old_pending["uid"]
                    
                    try:
                        # Calculate target date for old task
                        old_target_date = (datetime.now() + timedelta(days=old_date_offset)).strftime("%Y-%m-%d")
                        
                        # Save old task to Firestore
                        old_doc_id = get_schedule_doc_id(old_uid, old_target_date)
                        old_doc_ref = db.collection('schedules').document(old_doc_id)
                        
                        old_task_id = str(uuid.uuid4())
                        old_new_task = {
                            "id": old_task_id,
                            "task_name": old_task_name,
                            "time": old_time_str,
                            "type": "common",
                            "completed": False,
                            "completedAt": None,
                            "scheduledAt": datetime.now().isoformat(),
                            "graceMinutes": 30
                        }
                        
                        old_doc = old_doc_ref.get()
                        if not old_doc.exists:
                            old_doc_ref.set({
                                "userId": old_uid,
                                "date": old_target_date,
                                "status": "active",
                                "tasks": [old_new_task],
                                "created_at": datetime.utcnow().isoformat()
                            })
                        else:
                            from firebase_admin import firestore as fs
                            old_doc_ref.update({
                                "tasks": fs.ArrayUnion([old_new_task])
                            })
                        
                        print(f"[AUTO-CONFIRM] Successfully saved: {old_task_name}")
                    except Exception as e:
                        print(f"[AUTO-CONFIRM] Error saving previous task: {e}")
                
                # Store NEW task in pending confirmations
                pending_confirmations[session_id] = {
                    "task_name": task_name,
                    "time": time_str,
                    "date_offset": date_offset,
                    "uid": uid
                }
                
                # Ask for confirmation
                day_phrase = "tomorrow" if date_offset == 1 else "today"
                reply = f"I heard '{task_name}' at {time_str} for {day_phrase}. Is that correct? Say yes or no."
                
                return jsonify({
                    "action": "reply",
                    "reply": reply,
                    "intent": "task_creation",
                    "is_confirmation": True,
                    "task": {
                        "name": task_name,
                        "time": time_str,
                        "date_offset": date_offset,
                        "day_phrase": day_phrase
                    }
                }), 200

        # --- 4. Fallback: Schedule check ---
        if any(x in text for x in ["nothing more", "no more", "that is all", "that's all", "thats all", "all done", "nothing else", "no thanks", "finished", "all set"]):
             return jsonify({
                 "action": "close",
                 "reply": "Great, your plan is all set. Have a wonderful day!"
             }), 200

        # --- 5. Fallback: Schedule info ---
        today_date = datetime.now().strftime("%Y-%m-%d")
        doc_id = get_schedule_doc_id(uid, today_date)
        doc = db.collection('schedules').document(doc_id).get()
        
        if doc.exists:
             tasks = doc.to_dict().get('tasks', [])
             if "schedule" in text or "tasks" in text:
                 count = len([t for t in tasks if not t.get('completed')])
                 return jsonify({
                    "action": "reply",
                    "reply": f"You have {count} tasks remaining for today. Is there anything else you'd like to add or ask?"
                 }), 200
        
        return jsonify({
            "action": "reply", 
            "reply": "I'm listening. You can tell me what you did, ask me about past activities, or add a task to your schedule. Is there anything else for today?"
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@ai_bp.route("/check_profile/<uid>", methods=["GET"])
def check_profile(uid):
    try:
        from firebase_admin import firestore
        db = firestore.client()
        doc = db.collection('elder_profiles').document(uid).get()
        if doc.exists:
            return jsonify({"exists": True, "data": doc.to_dict()}), 200
        return jsonify({"exists": False}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@ai_bp.route("/create_profile", methods=["POST"])
def create_profile():
    try:
        from firebase_admin import firestore
        db = firestore.client()
        data = request.json
        uid = data.get('uid')
        
        if not uid:
            return jsonify({"error": "uid required"}), 400

        # Validate/Extract the 16 features (and basic info)
        profile_data = {
            "uid": uid,
            "name": data.get("name"),
            "age": data.get("age"),
            "long_term_illness": data.get("long_term_illness"),
            
            # Health & Wellbeing
            "sleep_well_1to5": data.get("sleep_well_1to5"),
            "tired_day_1to5": data.get("tired_day_1to5"),
            
            # Memory & Cognitive
            "forget_recent_1to5": data.get("forget_recent_1to5"),
            "difficulty_remember_tasks_1to5": data.get("difficulty_remember_tasks_1to5"),
            "forget_take_meds_1to5": data.get("forget_take_meds_1to5"),
            "tasks_harder_1to5": data.get("tasks_harder_1to5"),
            
            # Social & Emotional
            "lonely_1to5": data.get("lonely_1to5"),
            "sad_anxious_1to5": data.get("sad_anxious_1to5"),
            "social_talk_1to5": data.get("social_talk_1to5"),
            "enjoy_hobbies_1to5": data.get("enjoy_hobbies_1to5"),
            
            # App Preferences
            "comfortable_app_1to5": data.get("comfortable_app_1to5"),
            "reminders_helpful_1to5": data.get("reminders_helpful_1to5"),
            "reminders_right_time_1to5": data.get("reminders_right_time_1to5"),
            "reminders_preference": data.get("reminders_preference"), 
            
            # --- NEW: Default Tracking Metrics (Cold Start) ---
            "missed_meds_per_week": 0,
            "missed_tasks_per_week": 0,
            "avg_task_delay_min": 0,
            "snoozes_per_day": 0,
            
            "created_at": datetime.utcnow().isoformat()
        }

        # --- Run Prediction (Shared Logic) ---
        from app.services.ml_inference import predict_elder_risk
        risk_result = predict_elder_risk(profile_data)
        
        # Merge prediction into profile
        risk_result['prediction_updated_at'] = datetime.utcnow().isoformat()
        profile_data.update(risk_result)

        db.collection('elder_profiles').document(uid).set(profile_data, merge=True)
        return jsonify({"message": "Profile created", "profile": profile_data}), 201

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


