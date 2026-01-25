"""
Central ML inference service.

- Loads ALL Member1 models at startup
- Caches them in memory
- Exposes safe prediction helpers
"""

from pathlib import Path
from typing import Dict, Union
import joblib

# -------------------------------------------------
# In-memory cache
# -------------------------------------------------
MODEL_CACHE: Dict[str, Dict] = {}


# -------------------------------------------------
# Startup loader
# -------------------------------------------------
def init_models(project_root: Union[str, Path]) -> None:
    """
    Load Member1 meal-plan models ONCE at app startup
    """
    root = Path(project_root)
    model_dir = root / "ml" / "member1_meal_plan" / "trained"

    MODEL_CACHE["member1"] = {
        "calorie": joblib.load(model_dir / "calorie_model.pkl"),
        "protein": joblib.load(model_dir / "protein_model.pkl"),
        "carb": joblib.load(model_dir / "carb_model.pkl"),
        "fat": joblib.load(model_dir / "fat_model.pkl"),
        "mealplan": joblib.load(model_dir / "mealplan_model.pkl"),
        "label_encoders": joblib.load(model_dir / "label_encoders.pkl"),
        "feature_columns": joblib.load(model_dir / "feature_columns.pkl"),
    }

    print("[INFO] Member1 ML models loaded successfully")


# -------------------------------------------------
# Internal helper
# -------------------------------------------------
def _get_member1_models():
    if "member1" not in MODEL_CACHE:
        raise RuntimeError("Member1 models not loaded")
    return MODEL_CACHE["member1"]


# -------------------------------------------------
# Public API
# -------------------------------------------------
def predict_nutrition(features: dict) -> dict:
    from ml.member1_meal_plan.inference import predict_nutrition_core

    models = _get_member1_models()
    return predict_nutrition_core(features, models)