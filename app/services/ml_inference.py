"""ML inference loader and wrapper.

This module must only load trained models (from `ml/trained_models` or
an artifact store) and provide inference helpers. Training code lives in `ml/`.
"""
from pathlib import Path
from typing import Any
import joblib


MODEL_REGISTRY = {
    "vitals": "ml/trained_models/vitals_model.joblib",
}


def load_model(name: str) -> Any:
    path = Path(MODEL_REGISTRY.get(name, ""))
    if not path.exists():
        raise FileNotFoundError(f"Trained model not found: {path}")
    return joblib.load(path)


def predict_vitals(features):
    model = load_model("vitals")
    return model.predict([features])
