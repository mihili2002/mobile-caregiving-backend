import os
from pathlib import Path
import threading

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
# ✅ LOAD ENV FIRST
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
dotenv_path = BASE_DIR.parent / ".env"

if dotenv_path.exists():
    load_dotenv(dotenv_path=str(dotenv_path), override=True)
else:
    print(f"WARNING: .env not found at {dotenv_path}")


# =========================================================
# ✅ FASTAPI APP (ONLY ONCE)
# =========================================================
app = FastAPI(title="Mobile Caregiving Backend")


# =========================================================
# ✅ CORS — FLUTTER WEB + AUTH (PRE-FLIGHT SAFE)
# Flutter web uses random localhost ports.
# Authorization header triggers OPTIONS preflight.
# =========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# =========================================================
# ✅ STARTUP (ONLY ONCE)
# =========================================================
@app.on_event("startup")
def startup():
    # Firebase init (safe in dev)
    try:
        init_firebase()
        print("✅ Firebase initialized")
    except Exception as e:
        print("⚠️ Firebase not initialized (continuing). Reason:", str(e))

    # -----------------------------------------------------
    # ✅ ML MODELS (Member1)
    # project_root MUST be the folder that contains `ml/`
    # -----------------------------------------------------
    candidate_roots = [
        BASE_DIR,              # if main.py is at repo root
        BASE_DIR.parent,       # if main.py is inside app/
        BASE_DIR.parents[1],   # sometimes needed depending on layout
    ]

    project_root = None
    for cand in candidate_roots:
        if (cand / "ml").exists():
            project_root = cand
            break

    if project_root is None:
        project_root = BASE_DIR.parents[1]

    print("PROJECT_ROOT =", project_root)
    print(
        "Member1 trained exists =",
        (project_root / "ml" / "member1_meal_plan" / "trained").exists(),
    )

    ml_inference.init_models(project_root)
    print("Member1 ready =", ml_inference.member1_ready())

    try:
        load_models()
        print("✅ load_models() completed")
    except Exception as e:
        print("⚠️ load_models() failed. Reason:", str(e))

    # Chatbot service
    app.state.chatbot_service = ChatbotService()

    # Background workers
    try:
        threading.Thread(target=start_scheduler, daemon=True).start()
        threading.Thread(target=start_aggregator, daemon=True).start()
        print("✅ Background workers started.")
    except Exception as e:
        print("⚠️ Background workers failed:", str(e))


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
# ✅ CONVERTED FLASK ROUTE -> FASTAPI (use get_db())
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

        return {"message": "Implement your existing logic here (unchanged)"}

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
app.include_router(medication_routes.router)  # main.py
