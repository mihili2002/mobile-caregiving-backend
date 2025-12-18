from fastapi import FastAPI
from app.core.firebase import init_firebase
from app.api.routes import auth, patients, caregivers, health_records

app = FastAPI(title="Mobile Caregiving Backend")

# Initialize Firebase Admin (reads credentials path from env)
init_firebase()

# ✅ Root endpoint (ADD THIS)
@app.get("/")
async def root():
    return {"message": "Mobile Caregiving Backend is running"}

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Include API routers
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(caregivers.router)
app.include_router(health_records.router)
