from fastapi import APIRouter

from app.api.routes.elder.health_submissions import router as elder_health_router
from app.api.routes.elder.meal_plans import router as elder_mealplans_router

from app.api.routes.doctor.dashboard import router as doctor_dashboard_router
from app.api.routes.doctor.meal_plans import router as doctor_mealplans_router

api_router = APIRouter()

# Elder routes
api_router.include_router(elder_health_router)
api_router.include_router(elder_mealplans_router)

# Doctor routes
api_router.include_router(doctor_dashboard_router)
api_router.include_router(doctor_mealplans_router)
