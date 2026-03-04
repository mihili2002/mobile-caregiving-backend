# app/main.py
import threading
from datetime import datetime, timedelta
from pathlib import Path
import mimetypes
import re

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles

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

mimetypes.add_type("audio/webm", ".webm")
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("audio/ogg", ".ogg")

# =========================================================
# PROJECT PATHS
# =========================================================
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent.resolve()
DOTENV_PATH = PROJECT_ROOT / ".env"
UPLOAD_DIR = PROJECT_ROOT / "uploads"

if DOTENV_PATH.exists():
    load_dotenv(dotenv_path=str(DOTENV_PATH), override=True)
else:
    print(f"WARNING: .env not found at: {DOTENV_PATH}")

# =========================================================
# FASTAPI APP
# =========================================================
app = FastAPI(title="Mobile Caregiving Backend")

# =========================================================
# STATIC FILES
# =========================================================
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

print("PROJECT_ROOT =", PROJECT_ROOT)
print("UPLOAD_DIR   =", UPLOAD_DIR)
print("UPLOAD_DIR EXISTS? =", UPLOAD_DIR.exists())

app.mount("/static", StaticFiles(directory=str(UPLOAD_DIR)), name="static")

# =========================================================
# CORS (ALLOW ANY localhost PORT for dev)
# =========================================================
ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
_ORIGIN_RE = re.compile(ORIGIN_REGEX)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# =========================================================
# Preflight handler (middleware level - OPTIONS never 400)
# =========================================================
@app.middleware("http")
async def handle_preflight(request: Request, call_next):
    if request.method == "OPTIONS":
        origin = request.headers.get("origin")
        headers = {}

        if origin and _ORIGIN_RE.match(origin):
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
            headers["Access-Control-Allow-Headers"] = request.headers.get(
                "access-control-request-headers", "*"
            )
            headers["Access-Control-Allow-Methods"] = request.headers.get(
                "access-control-request-method", "GET,POST,PUT,DELETE,OPTIONS"
            )

        return Response(status_code=204, headers=headers)

    return await call_next(request)

# =========================================================
# Force CORS headers on ALL errors (prevents "CORS blocked" on 500/429)
# =========================================================
def _cors_headers_for_request(request: Request) -> dict:
    origin = request.headers.get("origin")
    if origin and _ORIGIN_RE.match(origin):
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "*",
        }
    return {}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=_cors_headers_for_request(request),
        )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
        headers=_cors_headers_for_request(request),
    )

# =========================================================
# STARTUP
# =========================================================
@app.on_event("startup")
def startup():
    # 1) Firebase
    try:
        init_firebase()
        print("✅ Firebase initialized")
    except Exception as e:
        print("⚠️ Firebase not initialized. Reason:", str(e))

    # 2) EmotionPredictor
    try:
        from app.services.emotion_predictor import EmotionPredictor

        emotion_models_dir = PROJECT_ROOT / "model"

        if not (emotion_models_dir / "emotion_model.pkl").exists():
            emotion_models_dir = Path(r"C:\Users\ASUS\Desktop\IME\mobile-caregiving-backend\model")

        model_path = emotion_models_dir / "emotion_model.pkl"
        scaler_path = emotion_models_dir / "scaler.pkl"
        encoder_path = emotion_models_dir / "label_encoder.pkl"

        if not model_path.exists():
            raise FileNotFoundError(f"emotion_model.pkl not found at {model_path}")
        if not scaler_path.exists():
            raise FileNotFoundError(f"scaler.pkl not found at {scaler_path}")
        if not encoder_path.exists():
            raise FileNotFoundError(f"label_encoder.pkl not found at {encoder_path}")

        app.state.emotion_predictor = EmotionPredictor(
            model_path=str(model_path),
            scaler_path=str(scaler_path),
            encoder_path=str(encoder_path),
        )
        print("✅ EmotionPredictor loaded!")
    except Exception as e:
        app.state.emotion_predictor = None
        print("❌ EmotionPredictor failed:", repr(e))

    # 3) ML Models
    try:
        if not (PROJECT_ROOT / "ml").exists():
            print(f"⚠️ WARNING: /ml folder not found at {PROJECT_ROOT}.")
        ml_inference.init_models(PROJECT_ROOT)
        print("✅ ML models loaded successfully")
    except Exception as e:
        print("⚠️ ML models not loaded. Reason:", str(e))

    # 4) AI models
    try:
        load_models()
        print("✅ load_models() completed")
    except Exception as e:
        print("⚠️ load_models() failed. Reason:", str(e))

    # 5) Chatbot service
    try:
        app.state.chatbot_service = ChatbotService()
        print("✅ ChatbotService initialized")
    except Exception as e:
        print("⚠️ ChatbotService init failed. Reason:", str(e))

    # 6) Background workers
    try:
        threading.Thread(target=start_scheduler, daemon=True).start()
        threading.Thread(target=start_aggregator, daemon=True).start()
        print("✅ Background workers started.")
    except Exception as e:
        print("⚠️ Background workers failed. Reason:", str(e))

# =========================================================
# BASIC ROUTES
# =========================================================
@app.get("/")
async def root():
    return {"status": "running", "message": "Caregiving Backend is active"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# =========================================================
# DAILY SUGGESTIONS ROUTE
# =========================================================
@app.get("/get_daily_suggestions/{uid}")
async def get_daily_suggestions(uid: str):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore client not initialized")

    try:
        doc = db.collection("elder_profiles").document(uid).get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Profile not found")

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

        therapy_ref = (
            db.collection("therapy_assignments")
            .where("elder_id", "==", uid)
            .stream()
        )
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

        meds_ref = (
            db.collection("patient_medications")
            .where("elder_id", "==", uid)
            .stream()
        )
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
# INCLUDE ROUTERS
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