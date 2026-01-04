import os
from pathlib import Path
from datetime import datetime, timedelta
import threading

from dotenv import load_dotenv

# =========================================================
# ✅ LOAD ENV FIRST (BEFORE ANY OTHER IMPORTS)
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(os.path.dirname(BASE_DIR), ".env")

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path, override=True)
else:
    print(f"WARNING: .env not found at {dotenv_path}")

# =========================================================
# ✅ NOW SAFE TO IMPORT EVERYTHING ELSE
# =========================================================
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import firebase_admin
from firebase_admin import credentials, firestore

from app.core.firebase import init_firebase
from app.api.routes import auth, patients, caregivers, ai_routes, schedule_routes, behavior_routes, medication_routes
from app.api.routes.elder import health_submissions, meal_plans as elder_meal_plans
from app.api.routes.doctor import dashboard as doctor_dashboard, meal_plans as doctor_meal_plans
from app.api.routes.chatbot_routes import router as chatbot_router

from app.services.chatbot_service import ChatbotService
from app.services import ml_inference

from app.services import load_models  # Used in Flask app previously
from app.workers.scheduler_worker import start_scheduler
from app.workers.aggregator_worker import start_aggregator


# =========================================================
# ✅ FASTAPI APP
# =========================================================
app = FastAPI(title="Mobile Caregiving Backend")

# ✅ CORS (Flutter Web runs on random localhost ports)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# ✅ FIREBASE SETUP
# =========================================================
db = None

def setup_firebase():
    """
    Initializes Firebase Admin only once and creates Firestore client.
    Uses the same serviceAccountKey.json logic your Flask code used.
    """
    global db

    if not firebase_admin._apps:
        key_path = os.path.join(BASE_DIR, "core", "serviceAccountKey.json")

        # Fallback to ../keys/serviceAccountKey.json
        if not os.path.exists(key_path):
            key_path = os.path.join(os.path.dirname(BASE_DIR), "keys", "serviceAccountKey.json")

        if not os.path.exists(key_path):
            raise FileNotFoundError(f"Firebase service account key not found at {key_path}")

        cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred)

    db = firestore.client()


# =========================================================
# ✅ STARTUP: INIT EVERYTHING ONCE
# =========================================================
@app.on_event("startup")
def startup():
    # --- Firebase (your old FastAPI init)
    try:
        init_firebase()
    except Exception as e:
        print(f"Warning: init_firebase() failed or already initialized: {e}")

    # --- Firebase admin + firestore client (from your Flask code)
    try:
        setup_firebase()
    except Exception as e:
        print(f"ERROR: Firebase setup failed: {e}")

    # --- ML models (FastAPI part)
    project_root = Path(__file__).resolve().parents[1]
    try:
        ml_inference.init_models(project_root)
    except Exception:
        print("Warning: ML models not loaded at startup; check ml/trained_models/")

    # --- AI models (from Flask app)
    try:
        load_models()
    except Exception as e:
        print(f"Warning: load_models() failed: {e}")

    # --- Chatbot service
    app.state.chatbot_service = ChatbotService()

    # --- Background jobs (non-blocking)
    try:
        threading.Thread(target=start_scheduler, daemon=True).start()
        threading.Thread(target=start_aggregator, daemon=True).start()
        print("INFO: Background workers started.")
    except Exception as e:
        print(f"Warning: Background workers failed to start: {e}")


# =========================================================
# ✅ BASIC ROUTES
# =========================================================
@app.get("/")
async def root():
    return {"status": "running", "message": "Caregiving Backend is active"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}


# =========================================================
# ✅ CONVERTED FLASK ROUTE -> FASTAPI
# =========================================================
@app.get("/get_daily_suggestions/{uid}")
async def get_daily_suggestions(uid: str):
    """
    Converted from Flask:
    GET /get_daily_suggestions/<uid>
    """
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore client not initialized")

    try:
        # A. Fetch Profile
        doc = db.collection('elder_profiles').document(uid).get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Profile not found")

        # B. COMMON SECTION & MEAL DETECTION
        common_ref = db.collection('common_routine_templates').where('uid', 'in', [uid, 'GLOBAL']).stream()
        common_tasks = []

        meal_schedule = {
            "breakfast": "08:00",
            "lunch": "13:00",
            "dinner": "20:00"
        }

        for c in common_ref:
            c_data = c.to_dict()
            t_str = c_data.get('time_string') or c_data.get('default_time') or "08:00"
            name = (c_data.get('task_name', '') or "").lower()

            if "breakfast" in name:
                meal_schedule["breakfast"] = t_str
            elif "lunch" in name:
                meal_schedule["lunch"] = t_str
            elif "dinner" in name:
                meal_schedule["dinner"] = t_str

            common_tasks.append({
                "task_name": c_data.get('task_name'),
                "default_time": t_str,
                "type": "common",
                "id": c.id
            })

        # C. THERAPY SECTION
        therapy_ref = db.collection('therapy_assignments').where('elder_id', '==', uid).stream()
        therapy_tasks = []
        for t in therapy_ref:
            t_data = t.to_dict()
            therapy_tasks.append({
                "activity_name": t_data.get('activity_name'),
                "duration": t_data.get('duration'),
                "instructions": t_data.get('instructions', ''),
                "type": "therapist",
                "id": t.id
            })

        # D. MEDICATION SECTION (SMART SCHEDULING)
        meds_ref = db.collection('patient_medications').where('elder_id', '==', uid).stream()
        med_tasks = []

        def calculate_time(base_time_str, timing_type):
            try:
                base = datetime.strptime(base_time_str, "%H:%M")
                if timing_type == "before_meal":
                    new_time = base - timedelta(minutes=30)
                elif timing_type == "after_meal":
                    new_time = base + timedelta(minutes=30)
                else:
                    new_time = base
                return new_time.strftime("%H:%M")
            except:
                return base_time_str

        for m_doc in meds_ref:
            doc_data = m_doc.to_dict()
            med_list = doc_data.get('medications', [])

            for m_data in med_list:
                if m_data.get('status') == 'active':
                    drug_name = m_data.get('drug_name', '')
                    if not drug_name:
                        continue

                    timing = m_data.get('timing', 'unknown')
                    freq = (m_data.get('frequency', '') or "").lower()

                    is_morning = False
                    is_noon = False
                    is_night = False

                    if "1-0-1" in freq or "bd" in freq or "twice" in freq or "2 times" in freq:
                        is_morning = True
                        is_night = True
                    elif "1-1-1" in freq or "tds" in freq or "three" in freq or "3 times" in freq:
                        is_morning = True
                        is_noon = True
                        is_night = True
                    elif "1-0-0" in freq or "od" in freq or "once" in freq or "1 time" in freq:
                        is_morning = True
                    elif "0-0-1" in freq:
                        is_night = True
                    else:
                        is_morning = True

                    med_id_base = m_doc.id + "_" + drug_name.replace(" ", "")

                    if is_morning:
                        t = calculate_time(meal_schedule['breakfast'], timing)
                        med_tasks.append({
                            "drug_name": drug_name,
                            "dosage": m_data.get('dosage'),
                            "time": t,
                            "timing_label": f"{timing.replace('_', ' ').title()} - Breakfast",
                            "type": "medication",
                            "id": med_id_base + "_am"
                        })

                    if is_noon:
                        t = calculate_time(meal_schedule['lunch'], timing)
                        med_tasks.append({
                            "drug_name": drug_name,
                            "dosage": m_data.get('dosage'),
                            "time": t,
                            "timing_label": f"{timing.replace('_', ' ').title()} - Lunch",
                            "type": "medication",
                            "id": med_id_base + "_noon"
                        })

                    if is_night:
                        t = calculate_time(meal_schedule['dinner'], timing)
                        med_tasks.append({
                            "drug_name": drug_name,
                            "dosage": m_data.get('dosage'),
                            "time": t,
                            "timing_label": f"{timing.replace('_', ' ').title()} - Dinner",
                            "type": "medication",
                            "id": med_id_base + "_pm"
                        })

        return {
            "common": common_tasks,
            "therapy": therapy_tasks,
            "medications": med_tasks
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Aggregator Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# ✅ INCLUDE FASTAPI ROUTERS
# =========================================================
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(caregivers.router)
app.include_router(health_submissions.router)
app.include_router(elder_meal_plans.router)
app.include_router(doctor_dashboard.router)
app.include_router(doctor_meal_plans.router)
app.include_router(chatbot_router)
app.include_router(ai_routes.router)
app.include_router(schedule_routes.router)
app.include_router(behavior_routes.router)
app.include_router(medication_routes.router)
