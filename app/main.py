from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.core.firebase import init_firebase
from app.api.routes import auth, patients, caregivers, health_records, risk
from app.services import ml_inference

app = FastAPI(title="Mobile Caregiving Backend")

# =========================================================
#  CORS CONFIG (REQUIRED FOR FLUTTER WEB)
# - Flutter Web runs on a random localhost port (e.g. 53544, 62226, etc.)
# - Browsers send OPTIONS preflight -> must return 200
# =========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],   # includes OPTIONS, POST, etc.
    allow_headers=["*"],
)

# =========================================================
# STARTUP
# =========================================================
@app.on_event("startup")
def startup():
    """Initialize third-party services and load ML models at app startup."""
    # Firebase should NOT crash the app in development
    try:
        init_firebase()
        print("✅ Firebase initialized")
    except Exception as e:
        print("⚠️ Firebase not initialized (continuing without it). Reason:", str(e))

    # Load ML models into memory
    project_root = Path(__file__).resolve().parents[1]
    try:
        ml_inference.init_models(project_root)
        print("✅ ML models loaded successfully")
    except Exception as e:
        print("⚠️ ML models not loaded at startup. Reason:", str(e))


# =========================================================
# BASIC ROUTES
# =========================================================
@app.get("/")
async def root():
    return {"message": "Mobile Caregiving Backend is running"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# =========================================================
# API ROUTERS
# =========================================================
app.include_router(auth.router, prefix="/api")
app.include_router(patients.router, prefix="/api")
app.include_router(caregivers.router, prefix="/api")
app.include_router(health_records.router, prefix="/api")
app.include_router(risk.router, prefix="/api")
