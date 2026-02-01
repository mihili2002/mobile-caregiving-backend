# app/main.py
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.firebase import init_firebase, get_db

# Routers
from app.api.routes import (
    auth,
    patients,
    caregivers,
    risk,
    ai_routes,
    schedule_routes,
    behavior_routes,
    medication_routes,
)
from app.api.routes.elder import health_submissions, meal_plans as elder_meal_plans
from app.api.routes.doctor import dashboard as doctor_dashboard, meal_plans as doctor_meal_plans
from app.api.routes.chatbot_routes import router as chatbot_router

# Services / workers
from app.services import ml_inference, load_models
from app.services.chatbot_service import ChatbotService
from app.workers.scheduler_worker import start_scheduler
from app.workers.aggregator_worker import start_aggregator


# =========================================================
# ✅ LOAD ENV (ONLY ONCE, BEFORE APP STARTUP)
# =========================================================
BASE_DIR = Path(__file__).resolve().parent          # .../app
PROJECT_ROOT = BASE_DIR.parent                      # repo root (contains /ml, .env, etc.)
DOTENV_PATH = PROJECT_ROOT / ".env"

if DOTENV_PATH.exists():
    load_dotenv(dotenv_path=str(DOTENV_PATH), override=True)
else:
    print(f"⚠️ WARNING: .env not found at: {DOTENV_PATH}")


# =========================================================
# ✅ FASTAPI APP (ONLY ONCE)
# =========================================================
app = FastAPI(title="Mobile Caregiving Backend")


# =========================================================
# ✅ CORS (ONLY ONCE)
# - Flutter Web runs on random localhost ports
# - Allow preflight OPTIONS
# =========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# ✅ STARTUP (ONLY ONCE)
# =========================================================
@app.on_event("startup")
def startup():
    # --- Firebase init (safe in dev)
    try:
        init_firebase()
        print("✅ Firebase initialized")
    except Exception as e:
        print("⚠️ Firebase not initialized (continuing). Reason:", str(e))

    # --- ML Models (Member1) - ensure PROJECT_ROOT contains /ml
    try:
        if not (PROJECT_ROOT / "ml").exists():
            print(f"⚠️ WARNING: /ml folder not found at {PROJECT_ROOT}. Check your project structure.")

        ml_inference.init_models(PROJECT_ROOT)
        print("✅ ML models loaded successfully")
        print("Member1 ready =", ml_inference.member1_ready())
    except Exception as e:
        print("⚠️ ML models not loaded at startup. Reason:", str(e))

    # --- AI models (if you use load_models)
    try:
        load_models()
        print("✅ load_models() completed")
    except Exception as e:
        print("⚠️ load_models() failed. Reason:", str(e))

    # --- Chatbot service
    try:
        app.state.chatbot_service = ChatbotService()
    except Exception as e:
        print("⚠️ ChatbotService init failed. Reason:", str(e))

    # --- Background workers
    try:
        threading.Thread(target=start_scheduler, daemon=True).start()
        threading.Thread(target=start_aggregator, daemon=True).start()
        print("INFO: Background workers started.")
    except Exception as e:
        print("⚠️ Background workers failed to start. Reason:", str(e))


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
# ✅ CONVERTED FLASK ROUTE -> FASTAPI (Your full logic kept)
# =========================================================
@app.get("/get_daily_suggestions/{uid}")
async def get_daily_suggestions(uid: str):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore client not initialized")

    try:
        # A. Fetch Profile
        doc = db.collection("elder_profiles").document(uid).get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Profile not found")

        # B. COMMON SECTION & MEAL DETECTION
        common_ref = (
            db.collection("common_routine_templates")
            .where("uid", "in", [uid, "GLOBAL"])
            .stream()
        )

        common_tasks = []
        meal_schedule = {"breakfast": "08:00", "lunch": "13:00", "dinner": "20:00"}

        for c in common_ref:
            c_data = c.to_dict() or {}
            t_str = c_data.get("time_string") or c_data.get("default_time") or "08:00"
            name = (c_data.get("task_name", "") or "").lower()

            if "breakfast" in name:
                meal_schedule["breakfast"] = t_str
            elif "lunch" in name:
                meal_schedule["lunch"] = t_str
            elif "dinner" in name:
                meal_schedule["dinner"] = t_str

            common_tasks.append(
                {
                    "task_name": c_data.get("task_name"),
                    "default_time": t_str,
                    "type": "common",
                    "id": c.id,
                }
            )

        # C. THERAPY SECTION
        therapy_ref = db.collection("therapy_assignments").where("elder_id", "==", uid).stream()
        therapy_tasks = []
        for t in therapy_ref:
            t_data = t.to_dict() or {}
            therapy_tasks.append(
                {
                    "activity_name": t_data.get("activity_name"),
                    "duration": t_data.get("duration"),
                    "instructions": t_data.get("instructions", ""),
                    "type": "therapist",
                    "id": t.id,
                }
            )

        # D. MEDICATION SECTION (SMART SCHEDULING)
        meds_ref = db.collection("patient_medications").where("elder_id", "==", uid).stream()
        med_tasks = []

        def calculate_time(base_time_str: str, timing_type: str) -> str:
            try:
                base = datetime.strptime(base_time_str, "%H:%M")
                if timing_type == "before_meal":
                    new_time = base - timedelta(minutes=30)
                elif timing_type == "after_meal":
                    new_time = base + timedelta(minutes=30)
                else:
                    new_time = base
                return new_time.strftime("%H:%M")
            except Exception:
                return base_time_str

        for m_doc in meds_ref:
            doc_data = m_doc.to_dict() or {}
            med_list = doc_data.get("medications", [])

            for m_data in med_list:
                if m_data.get("status") != "active":
                    continue

                drug_name = (m_data.get("drug_name") or "").strip()
                if not drug_name:
                    continue

                timing = m_data.get("timing", "unknown")
                freq = (m_data.get("frequency", "") or "").lower()

                is_morning = is_noon = is_night = False

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
                    t = calculate_time(meal_schedule["breakfast"], timing)
                    med_tasks.append(
                        {
                            "drug_name": drug_name,
                            "dosage": m_data.get("dosage"),
                            "time": t,
                            "timing_label": f"{timing.replace('_', ' ').title()} - Breakfast",
                            "type": "medication",
                            "id": med_id_base + "_am",
                        }
                    )

                if is_noon:
                    t = calculate_time(meal_schedule["lunch"], timing)
                    med_tasks.append(
                        {
                            "drug_name": drug_name,
                            "dosage": m_data.get("dosage"),
                            "time": t,
                            "timing_label": f"{timing.replace('_', ' ').title()} - Lunch",
                            "type": "medication",
                            "id": med_id_base + "_noon",
                        }
                    )

                if is_night:
                    t = calculate_time(meal_schedule["dinner"], timing)
                    med_tasks.append(
                        {
                            "drug_name": drug_name,
                            "dosage": m_data.get("dosage"),
                            "time": t,
                            "timing_label": f"{timing.replace('_', ' ').title()} - Dinner",
                            "type": "medication",
                            "id": med_id_base + "_pm",
                        }
                    )

        return {"common": common_tasks, "therapy": therapy_tasks, "medications": med_tasks}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Aggregator Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# ✅ INCLUDE ROUTERS (ONLY ONCE)
# =========================================================
app.include_router(auth.router, prefix="/api")
app.include_router(patients.router, prefix="/api")
app.include_router(caregivers.router, prefix="/api")
app.include_router(risk.router, prefix="/api")

app.include_router(health_submissions.router)
app.include_router(elder_meal_plans.router)
app.include_router(doctor_dashboard.router)
app.include_router(doctor_meal_plans.router)

app.include_router(chatbot_router)
app.include_router(ai_routes.router)
app.include_router(schedule_routes.router)
app.include_router(behavior_routes.router)
app.include_router(medication_routes.router)


