from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.core.firebase import init_firebase
from app.api.routes import auth, patients, caregivers
from app.api.routes.elder import health_submissions, meal_plans as elder_meal_plans
from app.api.routes.doctor import dashboard as doctor_dashboard, meal_plans as doctor_meal_plans
from app.api.routes.chatbot_routes import router as chatbot_router
from app.services.chatbot_service import ChatbotService
from app.services import ml_inference

app = FastAPI(title="Mobile Caregiving Backend")

# ✅ CORS (Flutter Web runs on random localhost ports)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    # Firebase
    init_firebase()

    # ML models
    project_root = Path(__file__).resolve().parents[1]
    try:
        ml_inference.init_models(project_root)
    except Exception:
        print("Warning: ML models not loaded at startup; check ml/trained_models/")

    # ✅ Chatbot service
    app.state.chatbot_service = ChatbotService()

@app.get("/")
async def root():
    return {"message": "Mobile Caregiving Backend is running"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# ✅ Include routers (all in one app)
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(caregivers.router)
app.include_router(health_submissions.router)
app.include_router(elder_meal_plans.router)

app.include_router(doctor_dashboard.router)
app.include_router(doctor_meal_plans.router)

app.include_router(chatbot_router)
