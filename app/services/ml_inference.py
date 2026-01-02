"""
ML inference loader and wrapper.

This module:
- Loads trained ML models at application startup
- Caches them in memory
- Exposes clean prediction helpers for FastAPI services

IMPORTANT:
- Models MUST be trained offline
- This module ONLY loads and runs inference
"""

from pathlib import Path
from typing import Any, Dict
import joblib


# ------------------------------------------------------------------
# Model Registry
# ------------------------------------------------------------------
# Logical name -> relative path from project root
MODEL_REGISTRY: Dict[str, str] = {
    # Member 1 – Personalized Meal Plan / Nutrition Targets
    "nutrition": "ml/member1_meal_plan/trained/nutrition_model.joblib",

    # Example for future expansion (Member 2, 3, 4)
    # "fall_detection": "ml/member2_fall_detection/trained/fall_model.joblib",
    # "anomaly": "ml/member3_anomaly_detection/trained/anomaly_model.joblib",
    # "risk": "ml/member4_risk_prediction/trained/risk_model.joblib",
}


# ------------------------------------------------------------------
# In-memory model cache
# ------------------------------------------------------------------
MODEL_CACHE: Dict[str, Any] = {}


# ------------------------------------------------------------------
# Startup loader (called once in main.py)
# ------------------------------------------------------------------
def init_models(base_path: str | Path = Path(".")) -> None:
    """
    Load all registered models into memory.

    Args:
        base_path: project root (defaults to current working directory)
    """
    bp = Path(base_path)

    for model_name, rel_path in MODEL_REGISTRY.items():
        model_path = (bp / rel_path).resolve()

        if not model_path.exists():
            print(f"[WARN] Model not found: {model_path}")
            continue

        MODEL_CACHE[model_name] = joblib.load(model_path)
        print(f"[INFO] Loaded model: {model_name}")


# ------------------------------------------------------------------
# Internal helper
# ------------------------------------------------------------------
def get_model(name: str):
    model = MODEL_CACHE.get(name)
    if model is None:
        raise RuntimeError(f"Model '{name}' not loaded")
    return model


# ------------------------------------------------------------------
# Member 1 – Meal Plan / Nutrition Prediction
# ------------------------------------------------------------------
# app/services/ml_inference.py

from ml.member1_meal_plan.inference import predict_nutrition as _predict

def predict_nutrition(features: dict) -> dict:
    """
    Wrapper for Member1 nutrition + meal plan prediction
    """
    return _predict(features)
