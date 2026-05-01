from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import joblib
import pandas as pd


ARTIFACTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "ml"
    / "member3_anomaly_detection"
    / "artifacts"
)

# These are the columns that your Pipeline expects (based on your printed pipeline)
# We'll load the official list from model_feature_columns.joblib too, but this helps readability.
YES_NO_FIELDS = {
    "Family_History_Mental_Illness",
    "Chronic_Illnesses",
    "Therapy",
    "Meditation",
}

STRESS_FIELDS = {"Financial_Stress", "Work_Stress"}

YES_NO_MAP = {
    "yes": 1.0, "y": 1.0, "true": 1.0, "1": 1.0, 1: 1.0, True: 1.0,
    "no": 0.0, "n": 0.0, "false": 0.0, "0": 0.0, 0: 0.0, False: 0.0,
}

STRESS_MAP = {
    "low": 0.0,
    "medium": 1.0,
    "high": 2.0,
}

def _to_float(v: Any) -> float:
    """Best-effort conversion to float."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s == "":
        return 0.0
    return float(s)


def _normalize_features(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert strings into what the trained pipeline expects.
    - Yes/No -> 1/0 for fields that were trained as numeric passthrough
    - Low/Medium/High -> 0/1/2 for stress fields trained as numeric
    """
    fixed: Dict[str, Any] = dict(raw)

    # Yes/No numeric passthrough fields
    for k in YES_NO_FIELDS:
        if k in fixed:
            v = fixed[k]
            if isinstance(v, str):
                key = v.strip().lower()
                if key in YES_NO_MAP:
                    fixed[k] = YES_NO_MAP[key]
                else:
                    # fallback: try float conversion
                    fixed[k] = _to_float(v)
            else:
                fixed[k] = _to_float(v)

    # Stress fields numeric mapping
    for k in STRESS_FIELDS:
        if k in fixed:
            v = fixed[k]
            if isinstance(v, str):
                key = v.strip().lower()
                if key in STRESS_MAP:
                    fixed[k] = STRESS_MAP[key]
                else:
                    fixed[k] = _to_float(v)
            else:
                fixed[k] = _to_float(v)

    return fixed


def _risk_level(p: float) -> str:
    """
    Convert probability to label.
    Tune thresholds as you like.
    """
    if p >= 0.70:
        return "High"
    if p >= 0.40:
        return "Medium"
    return "Low"


@dataclass
class RiskPrediction:
    probability: float
    level: str


class RiskPredictor:
    def __init__(self) -> None:
        # Load feature columns
        self.feature_columns = joblib.load(ARTIFACTS_DIR / "model_feature_columns.joblib")

        # Load the 4 trained pipelines (each is a Pipeline with ColumnTransformer + model)
        self.model_depression = joblib.load(ARTIFACTS_DIR / "model_depression.joblib")
        self.model_anxiety = joblib.load(ARTIFACTS_DIR / "model_anxiety.joblib")
        self.model_insomnia = joblib.load(ARTIFACTS_DIR / "model_insomnia.joblib")
        self.model_emotional = joblib.load(ARTIFACTS_DIR / "model_emotional_wellbeing.joblib")

    def predict(self, resident_id: str, features: Dict[str, Any]) -> Dict[str, Any]:
        # Normalize inputs to match training types
        fixed = _normalize_features(features)

        # Build row with ALL required features (missing -> 0)
        row = {col: fixed.get(col, 0) for col in self.feature_columns}
        X = pd.DataFrame([row], columns=self.feature_columns)

        # Predict probabilities
        dep_p = float(self.model_depression.predict_proba(X)[0][1])
        anx_p = float(self.model_anxiety.predict_proba(X)[0][1])
        ins_p = float(self.model_insomnia.predict_proba(X)[0][1])
        emo_p = float(self.model_emotional.predict_proba(X)[0][1])

        return {
            "resident_id": resident_id,
            "predictions": {
                "Depression_Risk": {"probability": dep_p, "level": _risk_level(dep_p)},
                "Anxiety_Risk": {"probability": anx_p, "level": _risk_level(anx_p)},
                "Insomnia_Risk": {"probability": ins_p, "level": _risk_level(ins_p)},
                "Emotional_WellBeing_Risk": {"probability": emo_p, "level": _risk_level(emo_p)},
            },
        }


# singleton
predictor = RiskPredictor()
