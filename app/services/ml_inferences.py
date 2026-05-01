import os
import joblib
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# Resolve Project Root (3 levels up from app/services/ml_inference.py)
# app/services/ml_inference.py -> app/services -> app -> Root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(CURRENT_DIR))

# Path to Labeling Model
LABELING_MODEL_PATH = os.path.join(BASE_DIR, "ml", "models", "artifacts", "best_model.pkl")
_labeling_model = None

def get_labeling_model():
    global _labeling_model
    if _labeling_model is None:
        if not os.path.exists(LABELING_MODEL_PATH):
            print(f"WARNING: Labeling model not found at {LABELING_MODEL_PATH}")
            return None
        try:
            _labeling_model = joblib.load(LABELING_MODEL_PATH)
        except Exception as e:
            print(f"Error loading labeling model: {e}")
            return None
    return _labeling_model

def predict_labels(snippets: list[str]) -> list[str]:
    model = get_labeling_model()
    if not model:
        return ["unknown"] * len(snippets)
    # model.predict returns numpy array of labels
    return model.predict(snippets).tolist()

# Path to Risk Prediction Model
RISK_MODEL_PATH = os.path.join(BASE_DIR, "ml", "models", "reminder_probability_model_clean.joblib")
_risk_pipeline = None

def get_pipeline():
    global _risk_pipeline
    if _risk_pipeline is None:
        if os.path.exists(RISK_MODEL_PATH):
            try:
                _risk_pipeline = joblib.load(RISK_MODEL_PATH)
            except Exception as e:
                print(f"Error loading risk model: {e}")
        else:
            print(f"WARNING: Risk model not found at {RISK_MODEL_PATH}")
    return _risk_pipeline

FEATURES = [
    "age",
    "long_term_illness",
    "sleep_well_1to5",
    "tired_day_1to5",
    "forget_recent_1to5",
    "difficulty_remember_tasks_1to5",
    "forget_take_meds_1to5",
    "tasks_harder_1to5",
    "lonely_1to5",
    "sad_anxious_1to5",
    "social_talk_1to5",
    "enjoy_hobbies_1to5",
    "comfortable_app_1to5",
    "reminders_helpful_1to5",
    "reminders_right_time_1to5",
    "reminders_preference",
    # weekly behavior fields (defaults at onboarding)
    "missed_meds_per_week",
    "missed_tasks_per_week",
    "avg_task_delay_min",
    "snoozes_per_day",
]

DEFAULT_WEEKLY = {
    "missed_meds_per_week": 0,
    "missed_tasks_per_week": 0,
    "avg_task_delay_min": 0,
    "snoozes_per_day": 0,
}

def to_tier(prob: float) -> str:
    if prob <= 0.32:
        return "Tier 1"
    elif prob <= 0.65:
        return "Tier 2"
    return "Tier 3"

def predict_elder_risk(data: dict) -> dict:
    """
    Predicts risk probability and tier using ML model.
    Data should contain frontend fields (uid, age, etc).
    Handles mapping Strings -> Ints/Category if needed.
    """
    pipe = get_pipeline()
    if not pipe:
        return {"prediction_probability": 0.5, "prediction_tier": "Tier 2 (Fallback)"}

    try:
        # DATA MAPPING (Frontend -> Model)
        # 1. Illness: "Yes" -> 1, "No" -> 0 (only if string; handle int safety)
        illness = data.get("long_term_illness")
        illness_val = 1 if illness == "Yes" or illness == 1 else 0
        
        # 2. Reminders: Map Frontend "Gentle Voice" etc -> Model "Same", "More"
        remind_pref = data.get("reminders_preference", "Same")
        if remind_pref not in ["More", "Same", "Fewer"]:
            remind_pref = "Same" 

        # Build feature dict
        features = {
            "age": float(data.get("age", 65)),
            "long_term_illness": illness_val,
            
            "sleep_well_1to5": int(data.get("sleep_well_1to5", 3)),
            "tired_day_1to5": int(data.get("tired_day_1to5", 3)),
            
            "forget_recent_1to5": int(data.get("forget_recent_1to5", 3)),
            "difficulty_remember_tasks_1to5": int(data.get("difficulty_remember_tasks_1to5", 3)),
            "forget_take_meds_1to5": int(data.get("forget_take_meds_1to5", 3)),
            "tasks_harder_1to5": int(data.get("tasks_harder_1to5", 3)),
            
            "lonely_1to5": int(data.get("lonely_1to5", 3)),
            "sad_anxious_1to5": int(data.get("sad_anxious_1to5", 3)),
            "social_talk_1to5": int(data.get("social_talk_1to5", 3)),
            "enjoy_hobbies_1to5": int(data.get("enjoy_hobbies_1to5", 3)),
            
            "comfortable_app_1to5": int(data.get("comfortable_app_1to5", 3)),
            "reminders_helpful_1to5": int(data.get("reminders_helpful_1to5", 3)),
            "reminders_right_time_1to5": int(data.get("reminders_right_time_1to5", 3)),
            "reminders_preference": remind_pref,
            
            # Use provided behavior stats or default to 0
            "missed_meds_per_week": int(data.get("missed_meds_per_week", 0)),
            "missed_tasks_per_week": int(data.get("missed_tasks_per_week", 0)),
            "avg_task_delay_min": float(data.get("avg_task_delay_min", 0)),
            "snoozes_per_day": float(data.get("snoozes_per_day", 0)),
        }

        # Create DataFrame with exact columns
        X = pd.DataFrame([features])
        X = X.reindex(columns=FEATURES, fill_value=0)
        
        prediction = pipe.predict(X)[0]
        prob = float(prediction)
        prob = float(np.clip(prob, 0, 1))
        tier = to_tier(prob)
        
        # Generate Reason
        reasons = []
        if features["missed_meds_per_week"] > 0:
            reasons.append("Recent missed medications")
        if features["missed_tasks_per_week"] > 3:
            reasons.append("High task incompletion")
        if features["forget_take_meds_1to5"] >= 4:
            reasons.append("Reported memory concerns")
        if features["age"] >= 80:
            reasons.append("Advanced age factor")
            
        reason_str = ", ".join(reasons) if reasons else "Routine profile assessment"
        
        return {
            "prediction_probability": prob,
            "prediction_tier": tier,
            "tier_reason_summary": reason_str
        }
    except Exception as e:
        print(f"Prediction Error: {e}")
        return {"prediction_probability": 0.5, "prediction_tier": "Error"}
