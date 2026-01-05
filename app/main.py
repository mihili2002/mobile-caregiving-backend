from fastapi import FastAPI
from app.core.firebase import init_firebase
from app.api.routes import auth, patients, caregivers
from app.api.routes.elder import health_submissions, meal_plans as elder_meal_plans
from app.api.routes.doctor import dashboard as doctor_dashboard, meal_plans as doctor_meal_plans
from app.services import ml_inference
from pathlib import Path

app = FastAPI(title="Mobile Caregiving Backend")


@app.on_event("startup")
def startup():
    """Initialize third-party services and load ML models at app startup."""
    # Initialize Firebase Admin (reads credentials path from env)
    init_firebase()

    # Load ML models into memory (no training here)
    project_root = Path(__file__).resolve().parents[1]
    try:
        ml_inference.init_models(project_root)
    except Exception:
        # Don't crash the whole app if models are missing; log and continue.
        print("Warning: ML models not loaded at startup; check ml/trained_models/")


@app.get("/")
async def root():
    return {"message": "Mobile Caregiving Backend is running"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# Include API routers
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(caregivers.router)
app.include_router(health_submissions.router)
app.include_router(elder_meal_plans.router)

app.include_router(doctor_dashboard.router)
app.include_router(doctor_meal_plans.router)

