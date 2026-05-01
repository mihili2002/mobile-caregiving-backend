"""
Central ML inference service.

- Loads ALL Member1 models at startup
- Caches them in memory
- Exposes safe prediction helpers
"""

from pathlib import Path
from typing import Dict, Union, Any
import joblib

# -------------------------------------------------
# In-memory cache
# -------------------------------------------------
MODEL_CACHE: Dict[str, Dict[str, Any]] = {}


# -------------------------------------------------
# Startup loader
# -------------------------------------------------
def init_models(project_root: Union[str, Path]) -> None:
    """
    Load Member1 meal-plan models ONCE at app startup.
    project_root MUST be the repo root that contains the `ml/` folder.
    """
    root = Path(project_root).resolve()
    model_dir = root / "ml" / "member1_meal_plan" / "trained"

    if not model_dir.exists():
        raise RuntimeError(
            f"Member1 trained models directory not found: {model_dir}\n"
            f"Given project_root={root}. Ensure project_root points to the repo root "
            f"that contains the `ml/` folder."
        )

    required_files = [
        "calorie_model.pkl",
        "protein_model.pkl",
        "carb_model.pkl",
        "fat_model.pkl",
        "mealplan_model.pkl",
        "label_encoders.pkl",
        "feature_columns.pkl",
    ]

    missing = [f for f in required_files if not (model_dir / f).exists()]
    if missing:
        raise RuntimeError(
            "Member1 model files missing in trained directory:\n"
            + "\n".join([str(model_dir / f) for f in missing])
        )

    MODEL_CACHE["member1"] = {
        "calorie": joblib.load(model_dir / "calorie_model.pkl"),
        "protein": joblib.load(model_dir / "protein_model.pkl"),
        "carb": joblib.load(model_dir / "carb_model.pkl"),
        "fat": joblib.load(model_dir / "fat_model.pkl"),
        "mealplan": joblib.load(model_dir / "mealplan_model.pkl"),
        "label_encoders": joblib.load(model_dir / "label_encoders.pkl"),
        "feature_columns": joblib.load(model_dir / "feature_columns.pkl"),
        "model_dir": str(model_dir),
    }

    print(f"[INFO] Member1 ML models loaded successfully from: {model_dir}")


def member1_ready() -> bool:
    """Quick health check for startup logs/tests."""
    m = MODEL_CACHE.get("member1")
    if not m:
        return False
    keys = ["calorie", "protein", "carb", "fat", "mealplan", "label_encoders", "feature_columns"]
    return all(m.get(k) is not None for k in keys)


# -------------------------------------------------
# Internal helper
# -------------------------------------------------
def _get_member1_models() -> Dict[str, Any]:
    models = MODEL_CACHE.get("member1")
    if not models or not member1_ready():
        raise RuntimeError("Member1 models not loaded")
    return models


# -------------------------------------------------
# Public API
# -------------------------------------------------
def predict_nutrition(features: dict) -> dict:
    from ml.member1_meal_plan.inference import predict_nutrition_core

    models = _get_member1_models()
    return predict_nutrition_core(features, models)
